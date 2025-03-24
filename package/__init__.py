from flask import Flask
from .appkey import app_config

app = Flask(__name__)
app.config['SECRET_KEY'] = app_config

from . import routes