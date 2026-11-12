from a2wsgi import ASGIMiddleware

from .main import app as asgi_app


application = ASGIMiddleware(asgi_app)
