import os
import json
import mysql.connector
import re
from flask import render_template, url_for, flash, redirect, request,session,jsonify
import google.generativeai as genai
import markdown
from . import app
from .recipeforms import InputForm
from .appkey import apikey  # Import API key

connection = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="ingredientbd"
)
cursor = connection.cursor()



@app.route("/", methods=["GET", "POST"])
def home():
    return render_template('homepage.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')






@app.route("/Precision_baking", methods=["GET", "POST"])
def Precision_baking():
    if request.method == "POST":
        Recipe_data = request.form.get("Recipe_input")
        
        if not Recipe_data:
            flash("⚠️ No input provided!", "warning")
            return redirect(url_for("Precision_baking"))  # Reload page if empty

        # Correctly pass Recipe_data using a query string
        return redirect(url_for("ingredientlist", recipe_data=Recipe_data))

    return render_template('input_page_precision_baking.html')

@app.route("/ingredients" , methods=['GET'])
def ingredientlist():
    Recipe_data_processing = request.args.get('recipe_data', None)
    print(Recipe_data_processing)
    
    genai.configure(api_key=apikey)
    model = genai.GenerativeModel("gemini-2.0-flash")
    
    if not Recipe_data_processing:
        flash("⚠️ No recipe data provided!", "warning")
        return redirect(url_for("Precision_baking"))


    def question_answer(context, prompt):
        result = model.generate_content(f"{context}\n{prompt}")
        output = result.text
        if "{" in output and "}" in output:
            dictionary = eval(output[output.find("{"):output.find("}")+1])
            return dictionary
    

    context_list = """I want you to give me a Python dictionary of ingredients from the recipe 
    with the format {ingredient1: [quantity, unit of measurement], ingredient2: [quantity, unit of measurement], ingredient3: [quantity, unit of measurement]}. 
    unit of measurement are like tsp,ozz also convert any value in fraction in float value such as this 2 ⅔ in 2.666667 and keep it till 2 decimal places and
    also if some values are like teaspoons,tablespoons make it in the abbreviation such as tsp,tbsp andReply with a python dictionary only and if any item is without 
    unit of measurement such as large egg or slices or anything without unit of measurement dont add it in the list.
    """
    
    def extract_no_unit_ingredients(ingredient_list):
        # Define standard units of measurement to exclude
        units = r'\b(?:tsp|teaspoons?|tbsp|tablespoons?|fl\s?oz|fluid ounces?|' \
                r'cups?|pt|pint|qt|quart|gal|gallon|' \
                r'mL|milliliters?|L|liters?|grams?|g|kilograms?|kg|milligrams?|mg|' \
                r'oz|ounces?|lb|pounds?|cl|centiliters?|dl|deciliters?)\b'

        # Split input into lines and clean up spaces
        ingredients = [item.strip() for item in ingredient_list.split("\n") if item.strip()]
        
        # Filter out ingredients that contain a standard unit
        no_unit_ingredients = [item for item in ingredients if not re.search(units, item, re.IGNORECASE)]
        
        return no_unit_ingredients


    result_list = question_answer(context_list, Recipe_data_processing)
    print(result_list)
    
    result_no_unit=extract_no_unit_ingredients(Recipe_data_processing)
    print(result_no_unit)
    
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

    def find_density(ingredient):
        sql_statement = f"SELECT density FROM ind WHERE ingredient = '{ingredient}' LIMIT 1;"
        cursor.execute(sql_statement)
        density = cursor.fetchone()
        if density:
            return density[0]
        else:
            context2 = "Tell me the average density in float format in python nothing else and only give me the number part"
            result2 = question_answer(context2, ingredient)
            density_value = float(result2)
            cursor.execute(f"INSERT INTO ind (ingredient, density) VALUES ('{ingredient}', {density_value});")
            connection.commit()
            return density_value

    output_list = []
    output_list = []
    for ingredient, (quantity, unit) in result_list.items():
        density = find_density(ingredient)
        volume = units_of_measurement.get(unit, 1)
        grams = round(density * volume * quantity, 2)
        print(str(ingredient),": "," density : ",density," volume : ",volume," quantity : ",quantity)
        output_list.append(f"{ingredient}: {grams} grams")

    for ingredient_no_unit in result_no_unit:
        output_list.append(ingredient_no_unit)
    
    return render_template('output_page_precision_baking.html', ingredient_output=output_list)







@app.route("/recipe_master", methods=['GET', 'POST'])
def recipe_master():
    if request.method == "POST":
        ingredients_list = request.form.get('ingredients_input', None)

        if not ingredients_list:
            flash("Please enter at least one ingredient.", "warning")
            return redirect(url_for('recipe_master'))  # Redirect back to input page
        else:
            print(f"✅ Redirecting with ingredients: {ingredients_list}")  # Debugging log
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
        return redirect(url_for('ind_to_recipe'))

    # Store ingredients in session for regeneration
    session['ingredients_list'] = ingredients_list

    def question_answer(context, prompt):
        try:
            response = model.generate_content(f"{context}\n{prompt}")

            # Extracting text from the response
            text_response = response.text if hasattr(response, "text") else response.candidates[0].content

            # Remove code block formatting (if present)
            cleaned_response = re.sub(r"```json\s*|\s*```", "", text_response).strip()
            return cleaned_response

        except Exception as e:
            return f"Error: {e}"

    # AI Prompt to return only one recipe
    context = """Provide **only one** recipe from the given ingredients.
    Reply strictly in a **valid JSON format**, containing:
    - 'name': recipe title
    - 'description': step-by-step instructions in **one string**, using numbered steps.
    Example:
    {"name": "Pancakes", "description": "1. Mix flour, eggs, and milk. 2. Cook on a pan. 3. Serve hot."}
    """

    prompt = f"Given these ingredients: {ingredients_list}, {context}"
    result = question_answer(context, prompt)
    print(f"🔍 Raw AI Response: {result}")  # Debugging log

    try:
        recipe_output = json.loads(result)
        
        # ✅ **Fix step splitting here**
        description = recipe_output.get("description", "")
        steps = re.split(r'\d+\.\s', description)[1:]  # Splits correctly at numbered steps

        formatted_steps = [f"Step {i + 1}: {step.strip()}" for i, step in enumerate(steps)]
        recipe_output["description"] = formatted_steps  # Now it's a **list of steps** instead of a single string

    except json.JSONDecodeError:
        print(f"❌ JSON Decoding Failed: {result}")  # Debugging log
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






@app.route("/treat_tech", methods=['GET', 'POST'])
def treat_tech():
    if request.method == "POST":
        dish_name = request.form.get('dish_name_input', None)

        if not dish_name:
            flash("Please enter at least one ingredient.", "warning")
            return redirect(url_for('dish_name'))  # Redirect back to input page
        else:
            print(f"✅ Redirecting with ingredients: {dish_name}")  # Debugging log
            return redirect(url_for('regenerate_recipe_v2', dish_name=dish_name))

    return render_template('input_page_treat_tech.html')

@app.route("/regenerate_recipe_v2", methods=['GET'], endpoint="regenerate_recipe_v2")
def regenerate_recipe_v2():
    dish_name = request.args.get('dish_name', '').strip()
    print(f"Received dish_name: '{dish_name}'")  # Debug

    if not dish_name:
        flash("Invalid dish name. Please enter a valid one.", "warning")
        print("Redirecting: Empty dish_name")  # Debug
        return redirect(url_for('home'))

    genai.configure(api_key=apikey)
    model = genai.GenerativeModel("gemini-2.0-flash")

    prompt = f"Provide a structured recipe for {dish_name}. Include:\n1. Ingredients\n2. Steps\n3. Cooking time\n4. Servings."
    print(f"Prompt sent to AI: {prompt}")  # Debug

    try:
        response = model.generate_content(prompt)
        print(f"Raw response: {response}")  # Debug
        print(f"Response text: '{response.text if response else None}'")  # Debug
        
        if not response or not response.text.strip():
            flash("No valid recipe found. Try another dish!", "danger")
            print("Redirecting: No valid response")  # Debug
            return redirect(url_for('home'))

        recipe_description = markdown.markdown(response.text.strip())
        print("Rendering recipe page")  # Debug

        return render_template("output_page_treat_tech.html", 
                               dish_name=dish_name, 
                               recipe_output={"name": dish_name, "description": recipe_description})

    except Exception as e:
        flash(f"Error generating recipe: {str(e)}", "danger")
        print(f"Redirecting: Exception occurred - {str(e)}")  # Debug
        return redirect(url_for('home'))