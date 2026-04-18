import azure.functions as func

from blueprints.day_lane import bp as day_lane_bp
from blueprints.night_lane import bp as night_lane_bp

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

app.register_blueprint(day_lane_bp)
app.register_blueprint(night_lane_bp)
