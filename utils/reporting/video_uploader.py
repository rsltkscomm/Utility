from pymongo import MongoClient
import gridfs
import os
from bson import ObjectId
from pytest_playwright.pytest_playwright import page

from utilities_py.excel_helper.test_context import TestContext

from utilities_py.baseclass.PW_BaseClass import PlaywrightActions

MONGO_URI = "mongodb://reportuser:Gxp2w6BRtk@10.200.20.11:27017/?authSource=admin"

client = MongoClient(MONGO_URI)
db = client["automation_reports"]
fs = gridfs.GridFS(db)


def upload_video(video_path, scenario_name, request):
    """Upload video to MongoDB GridFS and return the ID"""

    TestContext.method_name = request.node.name

    try:
        if not os.path.exists(video_path):
            print(f"❌ Video file does not exist: {video_path}")
            return None

        with open(video_path, "rb") as f:
            actions = PlaywrightActions(page)

            method_name = (TestContext.method_name or "test") + actions.add_time_to_name()

            video_id = fs.put(
                f,
                filename=method_name + ".webm",
                scenario=scenario_name,
                content_type="video/webm"
            )

        return str(video_id)

    except Exception as e:
        print(f"❌ Failed to upload video: {e}")
        return None

def get_video(video_id):
    """Retrieve video from GridFS by ID"""
    try:
        grid_out = fs.get(ObjectId(video_id))
        return grid_out.read()
    except Exception as e:
        print(f"❌ Failed to retrieve video: {e}")
        return None