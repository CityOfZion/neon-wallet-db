from .server import application
from .api_old import api_old
from .api import api

application.register_blueprint(api_old)
application.register_blueprint(api)

if __name__ == "__main__":
    application.run(host='0.0.0.0')
