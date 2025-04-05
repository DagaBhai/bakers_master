import os
import json
from json import JSONEncoder
import sqlite3  # Replaced pymysql with sqlite3
from flask import render_template, url_for, flash, redirect, request, session, jsonify
import google.generativeai as genai
import markdown
import re
from . import app
from .recipeforms import InputForm
from .appkey import apikey  # Import API key

# Basic routes
@app.route("/", methods=["GET", "POST"])
def home():
    return render_template('homepage.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

def get_db_connection():
    conn = sqlite3.connect('ingredientbd.db')
    conn.row_factory = sqlite3.Row  
    return conn

@app.route("/Precision_baking", methods=["GET", "POST"])
def Precision_baking():
    if request.method == "POST":
        Recipe_data = request.form.get("Recipe_input")
        print(f"Received input: {Recipe_data}")
        if not Recipe_data:
            flash("⚠️ No input provided!", "warning")
            return redirect(url_for("Precision_baking"))
        return redirect(url_for("ingredientlist", recipe_data=Recipe_data))
    return render_template('input_page_precision_baking.html')

@app.route("/ingredients", methods=['GET'])
def ingredientlist():
    Recipe_data_processing = request.args.get('recipe_data', None)
    print(f"Recipe data: {Recipe_data_processing}")
    
    if not Recipe_data_processing:
        print("No recipe data, redirecting...")
        flash("⚠️ No recipe data provided!", "warning")
        return redirect(url_for("Precision_baking"))

    genai.configure(api_key=apikey)
    model = genai.GenerativeModel("gemini-2.0-flash")

    def question_answer(context, prompt):
        try:
            result = model.generate_content(f"{context}\n{prompt}")
            output = result.text.strip()
            print(f"Gemini raw output: {output}")
            if "{" in output and "}" in output:
                dictionary = eval(output[output.find("{"):output.find("}")+1])
                return dictionary
            return output
        except Exception as e:
            print(f"Gemini API error: {e}")
            return None

    # Updated context to handle all vague measurements dynamically
    context_list = """I want you to give me a Python dictionary of ingredients from the recipe 
    with the format {ingredient1: [quantity, unit of measurement], ingredient2: [quantity, unit of measurement], ingredient3: [quantity, unit of measurement]}. 
    Units of measurement are like tsp, oz; convert fractions like 2 ⅔ to 2.67 (2 decimal places); 
    abbreviate teaspoons to tsp, tablespoons to tbsp; for any vague or non-standard measurements 
    (e.g., 'slice', 'large egg', 'pinch', 'dash', 'handful', etc.), use 'vague' as the unit and 
    estimate a reasonable quantity if not specified (e.g., 1 for 'large egg', 0.1 for 'pinch'). 
    Reply with a Python dictionary only."""

    units_of_measurement = {
        "tsp": 4.93, "teaspoon": 4.93, "teaspoons": 4.93,  
        "tbsp": 14.79, "tablespoon": 14.79, "tablespoons": 14.79,  
        "fl oz": 29.57, "fluid ounce": 29.57, "fluid ounces": 29.57,  
        "cup": 237, "cups": 237,  
        "pt": 473, "pint": 473, "pints": 473,  
        "qt": 946, "quart": 946, "quarts": 946,  
        "gal": 3785, "gallon": 3785, "gallons": 3785,  
        "mL": 1, "ml": 1, "milliliter": 1, "milliliters": 1,  
        "L": 1000, "l": 1000, "liter": 1000, "liters": 1000,  
        "cl": 10, "centiliter": 10, "centiliters": 10,  
        "dl": 100, "deciliter": 100, "deciliters": 100,    
        "g": 1, "gram": 1, "grams": 1,  
        "kg": 1000, "kilogram": 1000, "kilograms": 1000,  
        "mg": 0.001, "milligram": 0.001, "milligrams": 0.001,  
        "oz": 28.35, "ounce": 28.35, "ounces": 28.35,  
        "lb": 453.59, "pound": 453.59, "pounds": 453.59,  
    }

    def find_density(ingredient, cursor, conn):
        try:
            sql_statement = "SELECT density FROM ind WHERE ingredient = ? LIMIT 1"
            cursor.execute(sql_statement, (ingredient,))
            density = cursor.fetchone()
            if density:
                return float(density['density'])

            context2 = f"Provide the average density of {ingredient} as a float number only (e.g., 0.5), no text or explanation."
            result2 = question_answer(context2, ingredient)
            try:
                density_value = float(result2)
            except (ValueError, TypeError):
                context2_retry = f"Return only the average density of {ingredient} as a plain float number (e.g., 0.5), no words, no explanation."
                result2 = question_answer(context2_retry, ingredient)
                density_value = float(result2) if result2 else 1.0
            cursor.execute("INSERT OR IGNORE INTO ind (ingredient, density) VALUES (?, ?)", (ingredient, density_value))
            conn.commit()
            return density_value
        except Exception as e:
            print(f"Error in find_density for {ingredient}: {e}")
            return 1.0

    def find_vague_weight(ingredient, quantity, cursor, conn):
        try:
            sql_statement = "SELECT weight FROM vague_ind WHERE ingredient = ? LIMIT 1"
            cursor.execute(sql_statement, (ingredient,))
            weight = cursor.fetchone()
            if weight:
                return float(weight['weight']) * float(quantity)

            context3 = f"Provide the average weight in grams of '{ingredient}' as a float number only (e.g., 50.0), no text or explanation."
            result3 = question_answer(context3, ingredient)
            try:
                weight_value = float(result3)
            except (ValueError, TypeError):
                context3_retry = f"Return only the average weight in grams of '{ingredient}' as a plain float number (e.g., 50.0), no words, no explanation."
                result3 = question_answer(context3_retry, ingredient)
                weight_value = float(result3) if result3 else 10.0  # Default to 10g if no valid response
            cursor.execute("INSERT OR IGNORE INTO vague_ind (ingredient, weight) VALUES (?, ?)", (ingredient, weight_value))
            conn.commit()
            return weight_value * float(quantity)
        except Exception as e:
            print(f"Error in find_vague_weight for {ingredient}: {e}")
            return 10.0 * float(quantity)  # Fallback default

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Create tables if they don't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ind (
                ingredient TEXT PRIMARY KEY,
                density REAL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vague_ind (
                ingredient TEXT PRIMARY KEY,
                weight REAL
            )
        """)
        conn.commit()

        result_list = question_answer(context_list, Recipe_data_processing)
        print(f"Parsed ingredients: {result_list}")
        if not isinstance(result_list, dict):
            print("Gemini didn’t return a dict, falling back...")
            flash("⚠️ Failed to parse recipe ingredients! Check input format.", "error")
            return redirect(url_for("Precision_baking"))

        output_list = []
        for ingredient, (quantity, unit) in result_list.items():
            try:
                if unit.lower() == "vague":
                    grams = round(find_vague_weight(ingredient, quantity, cursor, conn), 2)
                    output_list.append(f"{ingredient}: {grams} grams")
                    print(f"{ingredient}: vague, quantity={quantity}, grams={grams}")
                else:
                    density = find_density(ingredient, cursor, conn)
                    volume = units_of_measurement.get(unit.lower(), 1)
                    grams = round(density * volume * float(quantity), 2)
                    output_list.append(f"{ingredient}: {grams} grams")
                    print(f"{ingredient}: density={density}, volume={volume}, quantity={quantity}")
            except (ValueError, TypeError) as e:
                print(f"Error processing {ingredient}: {e}")
                output_list.append(f"{ingredient}: Unable to calculate weight")

        conn.close()
        return render_template('output_page_precision_baking.html', ingredient_output=output_list)

    except Exception as e:
        print(f"Error in ingredientlist: {e}")
        if 'conn' in locals():
            conn.close()
        flash("⚠️ An error occurred while processing the recipe!", "error")
        return redirect(url_for("Precision_baking"))

# Recipe Master routes (unchanged)
@app.route("/recipe_master", methods=['GET', 'POST'])
def recipe_master():
    if request.method == "POST":
        ingredients_list = request.form.get('ingredients_input', None)
        if not ingredients_list:
            flash("Please enter at least one ingredient.", "warning")
            return redirect(url_for('recipe_master'))
        print(f"✅ Redirecting with ingredients: {ingredients_list}")
        return redirect(url_for('ind_to_recipe', ingredients_list=ingredients_list))
    return render_template('input_page_recipe_master.html')

@app.route("/ind_to_recipe", methods=['GET'])
def ind_to_recipe():
    ingredients_list = request.args.get('ingredients_list', None)
    print(f"🛑 Received ingredients in Recipelist: {ingredients_list}")

    genai.configure(api_key=apikey)
    model = genai.GenerativeModel("gemini-2.0-flash")
    
    if not ingredients_list:
        flash("No ingredients provided. Please enter ingredients.", "warning")
        return redirect(url_for('recipe_master'))

    session['ingredients_list'] = ingredients_list

    def question_answer(context, prompt):
        try:
            response = model.generate_content(f"{context}\n{prompt}")
            text_response = response.text if hasattr(response, "text") else response.candidates[0].content
            cleaned_response = re.sub(r"```json\s*|\s*```", "", text_response).strip()
            return cleaned_response
        except Exception as e:
            return f"Error: {e}"

    context = """Provide **only one** recipe from the given ingredients.
    Reply strictly in a **valid JSON format**, containing:
    - 'name': recipe title
    - 'description': step-by-step instructions in **one string**, using numbered steps.
    Example:
    {"name": "Pancakes", "description": "1. Mix flour, eggs, and milk. 2. Cook on a pan. 3. Serve hot."}
    """

    prompt = f"Given these ingredients: {ingredients_list}, {context}"
    result = question_answer(context, prompt)
    print(f"🔍 Raw AI Response: {result}")

    try:
        recipe_output = json.loads(result)
        description = recipe_output.get("description", "")
        steps = re.split(r'\d+\.\s', description)[1:]
        formatted_steps = [f"Step {i + 1}: {step.strip()}" for i, step in enumerate(steps)]
        recipe_output["description"] = formatted_steps
    except json.JSONDecodeError:
        print(f"❌ JSON Decoding Failed: {result}")
        recipe_output = {"name": "Error", "description": ["Invalid AI response format"]}

    print(f"✅ Recipe Output: {recipe_output}")
    return render_template("output_page_recipe_master.html", recipe_output=recipe_output)

@app.route("/regenerate_recipe")
def regenerate_recipe():
    ingredients_list = session.get('ingredients_list')
    if not ingredients_list:
        flash("No ingredients found. Please enter ingredients again.", "warning")
        return redirect(url_for('recipe_master'))
    return redirect(url_for('ind_to_recipe', ingredients_list=ingredients_list))

# Treat Tech routes (unchanged)
@app.route("/treat_tech", methods=['GET', 'POST'])
def treat_tech():
    if request.method == "POST":
        dish_name = request.form.get('dish_name_input', None)
        if not dish_name:
            flash("Please enter a dish name.", "warning")
            return redirect(url_for('treat_tech'))
        print(f"✅ Redirecting with dish: {dish_name}")
        return redirect(url_for('regenerate_recipe_v2', dish_name=dish_name))
    return render_template('input_page_treat_tech.html')

@app.route("/regenerate_recipe_v2", methods=['GET'], endpoint="regenerate_recipe_v2")
def regenerate_recipe_v2():
    dish_name = request.args.get('dish_name', '').strip()
    print(f"Received dish_name: '{dish_name}'")

    if not dish_name:
        flash("Invalid dish name. Please enter a valid one.", "warning")
        print("Redirecting: Empty dish_name")
        return redirect(url_for('treat_tech'))

    genai.configure(api_key=apikey)
    model = genai.GenerativeModel("gemini-2.0-flash")

    prompt = f"Provide a structured recipe for {dish_name}. Include:\n1. Ingredients\n2. Steps\n3. Cooking time\n4. Servings. TRY TO GIVE ingredients in grams"
    print(f"Prompt sent to AI: {prompt}")

    try:
        response = model.generate_content(prompt)
        print(f"Raw response: {response}")
        if not response or not response.text.strip():
            flash("No valid recipe found. Try another dish!", "danger")
            print("Redirecting: No valid response")
            return redirect(url_for('treat_tech'))

        recipe_description = markdown.markdown(response.text.strip())
        print("Rendering recipe page")
        return render_template("output_page_treat_tech.html", 
                               dish_name=dish_name, 
                               recipe_output={"name": dish_name, "description": recipe_description})
    except Exception as e:
        flash(f"Error generating recipe: {str(e)}", "danger")
        print(f"Redirecting: Exception occurred - {str(e)}")
        return redirect(url_for('treat_tech'))

# Debug routes on startup
print("Registered routes:")
print(app.url_map)
