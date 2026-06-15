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
    DEPLOY_CHECKLIST_RESULTS = ONEDRIVE_BASE_PATH / "DeploymentCheckListResults"
    REG_CHECKLIST_RESULTS = ONEDRIVE_BASE_PATH / "RegressionResults"
    DYNAMIC_PATH = Path(os.getcwd()) / "loc_utils" / "data" / "DynamicFile"
    DOWNLOADED_FILE_PATH = Path(os.getcwd()) / "loc_utils" / "data" / "downloaded_file"
    UPLOAD_FILE_PATH = Path(os.getcwd()) / "loc_utils" / "data" / "UploadFiles"
    PROJECT_NAME = os.getenv("PROJECT_NAME")
    PROJECT_DIR = os.path.join(os.getcwd(), "features")
    MARKETING_STAR_DAILY_PATH = ONEDRIVE_BASE_PATH / "Marketing Star Daily Checklist"
    MARKETING_STAR_DEPLOY_PATH = ONEDRIVE_BASE_PATH / "MarketingStar DeploymentChecklist"
    MARKETING_STAR_REGRESSION_PATH = ONEDRIVE_BASE_PATH / "Marketing Star Regression"

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
    def get_daily_checklist_result_path():
        return FrameworkConstants.DAILY_CHECKLIST_RESULTS

    @staticmethod
    def get_deploy_checklist_result_path():
        return FrameworkConstants.DEPLOY_CHECKLIST_RESULTS

    @staticmethod
    def get_regression_checklist_result_path():
        return FrameworkConstants.REG_CHECKLIST_RESULTS

    @staticmethod
    def get_MK_daily_checklist_result_path():
        return FrameworkConstants.MARKETING_STAR_DAILY_PATH

    @staticmethod
    def get_MK_deploy_checklist_result_path():
        return FrameworkConstants.MARKETING_STAR_DEPLOY_PATH

    @staticmethod
    def get_MK_regression_checklist_result_path():
        return FrameworkConstants.MARKETING_STAR_REGRESSION_PATH

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