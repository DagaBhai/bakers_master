#here is how the recipe will be given by the user
from flask_wtf import FlaskForm
from wtforms import StringField,SubmitField
from wtforms.validators import DataRequired,Length

class InputForm(FlaskForm):
    Recipe_input= StringField("RECIPE",validators=[DataRequired(),Length(min=10 , max=1000)])
    submit=SubmitField("submit")
