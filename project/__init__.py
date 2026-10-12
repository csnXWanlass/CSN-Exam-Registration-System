from urllib.parse import quote_plus

from flask import Flask  # web framework
from flask_sqlalchemy import SQLAlchemy  # 
from flask_login import LoginManager
import os
from dotenv import find_dotenv, load_dotenv


db = SQLAlchemy()               # creates an SQLAlchemy object
login_manager = LoginManager()


def create_app():
    app = Flask(__name__)

    load_dotenv()  # load environment variables from .env file into memory
    # Print the location of the .env file and the value MYSQL_DB for debugging purposes.
    # flush writes the output immediately instead of buffering it
    print("Reading", find_dotenv(), "| MYSQL_DB =", os.getenv("MYSQL_DB"), flush=True)
    
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    mysql_host = os.getenv('MYSQL_HOST')  # pull the MySQL connection info from the .env file
    mysql_user = os.getenv('MYSQL_USER')
    mysql_password = os.getenv('MYSQL_PASSWORD')
    mysql_db = os.getenv('MYSQL_DB')

    # Dictionary of required MySQL environment variables and their values
    required_keys = {
        'MYSQL_HOST': mysql_host,
        'MYSQL_USER': mysql_user,
        'MYSQL_PASSWORD': mysql_password,
        'MYSQL_DB': mysql_db
    }
    # create a list of missing environment variables
    # output the key when the value is None or empty string
    #
    # required_keys.items() is a built-in method for dictionaries
    #     that returns a view object of the dictionary's key-value pairs
    missing_keys = [key for key, value in required_keys.items() if not value]

    # if there are missing environment variables, output an error code wiht needed keys
    if missing_keys:
        raise RuntimeError(f"Missing environment variables: {', '.join(missing_keys)}", flush=True)

    # flask_sqlalchemy: SQLALChemy_DATABASE_URI needed for SQLAlchemy to connect to the database.
    # FORMAT - dialect+driver://username:password@host:port/database
    app.config['SQLALCHEMY_DATABASE_URI'] = (
        # read mysql with pymysql driver, append username to URI
        f"mysql+pymysql://{required_keys['MYSQL_USER']}:"
        # quote_plus: fixes special characters in the password for the URI
        f"{quote_plus(required_keys['MYSQL_PASSWORD'])}@"
        # append host and database name to URI
        f"{required_keys['MYSQL_HOST']}/{required_keys['MYSQL_DB']}"
    )
    print("URI set:", 'SQLALCHEMY_DATABASE_URI' in app.config, flush=True)
    db.init_app(app)

    with app.app_context():
        from .models import User
        db.create_all()

    return app


