import os
import logging
from flask import Flask, session
from werkzeug.middleware.proxy_fix import ProxyFix
from functools import wraps
from config_manager import load_config, get_config_value

# Configure logging for debugging
logging.basicConfig(level=logging.DEBUG)

# create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "qsowhat-default-secret-key")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configure upload settings
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'

# Load configuration
app.config['QSOWHAT_CONFIG'] = load_config()

# Admin credentials — password comes from the ADMIN_PASSWORD env var (a Fly secret),
# never from config.json, since that file is committed to a public repo.
ADMIN_USERNAME = get_config_value('station.call_sign', 'N0CALL')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', get_config_value('site.admin_password', 'changeme'))

# Create upload directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def admin_required(f):
    """Decorator to require admin authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            from flask import redirect, url_for
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# Template context processors
@app.context_processor
def inject_config():
    """Make config values available in all templates"""
    return {
        'config': app.config['QSOWHAT_CONFIG'],
        'get_config': get_config_value
    }

# Import routes after app initialization
import routes  # noqa: F401
