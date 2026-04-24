import os
from pathlib import Path
import platform
from dotenv import load_dotenv
load_dotenv()

class FrameworkConstants():
    BASE_PATH = (
        Path("C:/AQApycred")
        if platform.system().lower() == "windows"
        else Path.home() / "AQApycred"
    )
    ONEDRIVE_BASE_PATH = Path.home() / "OneDrive - RESULTICKS" / "Automation" / "Resulticks"
    DAILY_CHECKLIST_RESULTS = ONEDRIVE_BASE_PATH / "DailyCheckListResults"
    DYNAMIC_PATH = Path(os.getcwd()) / "loc_utils" / "data" / "DynamicFile"
    DOWNLOADED_FILE_PATH = Path(os.getcwd()) / "loc_utils" / "data" / "downloaded_file"
    UPLOAD_FILE_PATH = Path(os.getcwd()) / "loc_utils" / "data" / "UploadFiles"
    PROJECT_NAME = os.getenv("PROJECT_NAME")
    PROJECT_DIR = os.path.join(os.getcwd(), "features")

    @staticmethod
    def get_download_file_path():
        return FrameworkConstants.DOWNLOADED_FILE_PATH

    @staticmethod
    def get_dynamic_file_path():
        return FrameworkConstants.DYNAMIC_PATH / "audiencedata.ini"

    @staticmethod
    def get_default_file_path():
        return FrameworkConstants.BASE_PATH / FrameworkConstants.PROJECT_NAME

    @staticmethod
    def get_credential_file_path():
        return FrameworkConstants.BASE_PATH / "credentials.json"

    @staticmethod
    def get_properties_path():
        return FrameworkConstants.get_default_file_path() / "Properties"

    @staticmethod
    def get_script_details_file():
        return FrameworkConstants.get_default_file_path() / "ScriptDetails.xlsx"

    @staticmethod
    def get_suite_name_file():
        return FrameworkConstants.get_default_file_path() / "SuiteNameFile.xlsx"

    @staticmethod
    def get_test_data_path():
        return FrameworkConstants.ONEDRIVE_BASE_PATH / "AQAcred" / FrameworkConstants.PROJECT_NAME

    @staticmethod
    def get_feature_file(*paths):
        return os.path.join(FrameworkConstants.PROJECT_DIR, *paths)

    @staticmethod
    def get_upload_files(file_name):
        return os.path.join(FrameworkConstants.UPLOAD_FILE_PATH, file_name)

    @staticmethod
    def get_daily_checklist_result_path(self):
        return FrameworkConstants.DAILY_CHECKLIST_RESULTS

    @staticmethod
    def get_team_data_file(user_name, environment):
        return (
                FrameworkConstants.get_test_data_path()
                / "TestData"
                / f"{user_name}_{environment}"
                / "Team"
        )

    @staticmethod
    def get_daily_checklist_result_path():
        return FrameworkConstants.DAILY_CHECKLIST_RESULTS

    @staticmethod
    def get_daily_checklist_path():
        return (
                FrameworkConstants.ONEDRIVE_BASE_PATH
                / "AQAcred"
                / FrameworkConstants.PROJECT_NAME
                / "DailyChecklistResults"
        )