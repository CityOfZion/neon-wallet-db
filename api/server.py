from flask import Flask
from flask_cors import CORS, cross_origin

application = Flask(__name__)
CORS(application)
