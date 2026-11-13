from datetime import datetime

from functools import wraps # adds a wrapper so we can redirect if not logged in
from flask import session, jsonify, redirect, url_for, request

from project import db
from project.models import Campus, Rooms, Users, Exams, Sessions, Registrations


## HELPERS ##

# FUNCTIONS #
def get_current_user():
    """Return the logged-in Users row, or None if there's no login or the cookie is stale."""
    user_id = session.get('user_id')
    if user_id is None:
        return None
    return db.session.get(Users, int(user_id))

def parse_date(text):
    """Turn text like '2026-10-14' into a date. Return None if it isn't one."""
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None

# DECORATORS #
def login_required(view):
    """ Deprecated, but functional.
    Require an active login, else redirect the user to the home page or return an error.
    """
    # "view" is chosen because flask calls the route functions "view" functions
    @wraps(view)
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:  # if the user ID is not in a session cookie
            # if it's because user session expired
            if request.method == 'POST':
                return jsonify(error='Session expired. Please log in again.'), 401
            return redirect(url_for('Index'))  # redirect home
        return view(*args, **kwargs)
    return wrapped

def role_required(*roles, page=False):
    """Require a logged-in user, optionally with one of `roles`.

    JSON routes (routes that return a jsonify call) answer a denied request with a 401/403
        JSON error.
    Page routes (routes that return a render_template call) redirect to the home page when
        access is denied.
    """
    # "view" is chosen because flask calls the route functions "view" functions
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            def deny(status, message):
                if page:
                    return redirect(url_for('Index'))
                return jsonify(error=message), status

            user = get_current_user()
            if user is None:                          # not logged in, or a stale cookie
                session.clear()
                return deny(401, 'Session expired. Please log in again.')

            # If a role is specified and the logged-in user is not a member, then deny.
            if roles and user.role not in roles:      # no roles listed means any logged-in user
                return deny(403, 'You do not have access to this page.')

            return view(*args, **kwargs)
        return wrapped
    return decorator