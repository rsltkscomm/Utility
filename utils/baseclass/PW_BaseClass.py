import os
import re
import time
from datetime import datetime
import inspect
from pathlib import Path

from utils.baseclass.WebActions import WebActions

class PlaywrightActions(WebActions):

    def __init__(self, page):
        self.page = page
        self.current_frame = None
        self.context = page.context

    # ---------------- Navigation ---------------- #

    def navigate(self, url):
        """Navigate to URL with proper wait"""
        self.page.goto(url, wait_until="domcontentloaded", timeout=60000)

    # ---------------- Click ---------------- #

    def click_element(self, locator):
        """Wait for element then click"""
        element = self.page.locator(locator)
        element.wait_for(state="visible", timeout=15000)
        element.click()
        return True;

    # ---------------- Enter Text ---------------- #

    def enter_value(self, locator, value):
        """Enter value after ensuring element is visible"""
        element = self.page.locator(locator)
        element.wait_for(state="visible", timeout=30000)
        element.click()
        element.clear()
        element.press_sequentially(value )
        return True

    # ---------------- Get Attribute ---------------- #

    def get_attribute(self, locator, attribute):
        """Return attribute value"""
        element = self.page.locator(locator)
        element.wait_for(state="attached", timeout=10000)
        return element.get_attribute(attribute)

    # ---------------- Get Text ---------------- #

    def get_value(self, locator):
        """Return element text safely"""
        element = self.page.locator(locator)
        element.wait_for(state="visible", timeout=30000)
        text = element.text_content()
        return text.strip() if text else ""

    # ---------------- Keyboard ---------------- #

    def click_tab(self):
        """Press TAB key"""
        self.page.keyboard.press("Tab")

    def click_enter(self):
        """Press TAB key"""
        self.page.keyboard.press("Enter")

    # ---------------- Utility Wait ---------------- #

    from playwright.sync_api import TimeoutError

    def wait_for_element(self, locator, timeout=15000):
        """Explicit wait for element"""
        try:
            self.page.locator(locator).wait_for(state="visible", timeout=timeout)
            return True
        except TimeoutError:
            return False

    # ---------------- Check Visible ---------------- #

    def is_visible(self, locator):
        """Check if element is visible"""
        return self.page.locator(locator).is_visible()

    # ---------------- Get Page Title ---------------- #

    def get_page_title(self):
        """Return page title"""
        return self.page.title()

    # ---------------- Get Current URL ---------------- #

    def get_current_url(self):
        """Return current URL"""
        return self.page.url

    # ---------------- Find Elements ---------------- #
    def locators(self, selector):
        locator = self.page.locator(selector)
        count = locator.count()
        elements = []
        for i in range(count):
            elements.append(locator.nth(i))
        return elements

    def locator(self, selector):
        return self.page.locator(selector)

    # ---------REPLACE THE VALUE OF LOCATOR -----------#
    def replace_place_holder(self, locator: str, *values) -> str:
        try:
            if not values:
                return locator
            updated_locator = locator
            if len(values) >= 1:
                updated_locator = updated_locator.replace("PLACE_HOLDER", str(values[0]))
            if len(values) >= 2:
                updated_locator = updated_locator.replace("TEMP", str(values[1]))
            return updated_locator
        except Exception as e:
            print(f"[ERROR] replace_placeholder: {e}")
            return locator

    # ---------------- Upload File ---------------- #

    def upload_file(self, locator, file_name) -> bool:
        try:
            element = self.page.locator(locator)
            element.wait_for(state="attached", timeout=15000)
            element.set_input_files(file_name)
            return True
        except Exception:
            return False

    #---------------- DELETE FILE --------------------------#
    def delete_file(self, file_path):
        if os.path.exists(file_path):
            os.remove(file_path)

# ------------------JAVA SCRIPT EXECUTOR METHODS --------------------- #

    def js_scroll_to_element(self, locator):
        """Scroll element into view"""
        element = self.page.locator(locator)
        element.evaluate("el => el.scrollIntoView()")

    def scroll_to_bottom(self):
        try:
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            return True
        except Exception:
            return False

    def js_click(self, locator):
        """Click element using JavaScript"""
        element = self.page.locator(locator)
        element.evaluate("el => el.click()")

    def js_enter_value(self, locator, value):
        """Enter value using JavaScript"""
        element = self.page.locator(locator)
        element.evaluate("(el, value) => el.value = value", value)

    def js_get_text(self, locator):
        """Get text using JavaScript"""
        element = self.page.locator(locator)
        return element.evaluate("el => el.innerText")

    def js_highlight(self, locator):
        """Highlight element in UI"""
        element = self.page.locator(locator)
        element.evaluate("el => el.style.border='3px solid red'")

#------------- Select List Elements -----------------------------
    def select_list_elements(self, elements_path, input_text):
        try:
            locator = self.page.locator(elements_path)
            count = locator.count()

            if count == 0:
                return False

            for i in range(count):
                option = locator.nth(i)
                text = option.inner_text().strip()

                if input_text.lower() in text.lower() or text.lower() == input_text.lower():
                    option.scroll_into_view_if_needed()
                    option.click()
                    return True

            return False

        except Exception:
           return False

#-----------------------Hover----------------------------------

    def hover_element(self, locator):
        """Hover element in UI"""
        self.page.locator(locator).hover()

#-----------------Add Time to name----------------------

    def add_time_to_name(self):
        try:
            timestamp = datetime.now().strftime("%I%M%S_%d%m%Y_%p")
            return timestamp
        except Exception as e:
            raise e

    def wait_for_invisibility(self, locator, timeout_sec=30):
        try:
            self.page.locator(locator).first.wait_for(
                state="hidden",
                timeout=timeout_sec * 1000
            )
            return True
        except TimeoutError:
            return False

    def is_not_empty(self, value) -> bool:
        """Check if value is not None and not empty/blank"""
        return value is not None and str(value).strip() != ""

    def javaScriptScrollIntoView(self, locator):
        element = self.page.locator(locator)
        element.wait_for(state="attached", timeout=10000)
        element.scroll_into_view_if_needed()

    def is_element_present(self, locator) -> bool:
        try:
            return self.page.locator(locator).count() > 0
        except Exception:
            return False


    def writeLogger(self, expression: bool, passLog: str, failLog: str) -> bool:
        # Get caller details (similar to Java StackTrace)
        frame = inspect.stack()[1]
        location = f"{frame.filename}.{frame.function}():{frame.lineno}"

        message = f"{passLog if expression else failLog} [{location}]"

        if expression:
            print("Pass : " + message)
        else:
            print("Fail : " + message)

        self.takeScreenshot()
        return expression

    def takeScreenshot(self):
        return self.take_screenshot("Screenshot", None)

    def take_screenshot(self, screenshot_name, element=None) -> str:
        try:
            loc = self.page.locator(element) if element else None

            # Highlight if element exists
            if loc:
                self.js_highlight(element)

            # File name + folder
            timestamp = datetime.now().strftime("%m_%d_%H%M_%S")
            file_name = f"{screenshot_name}_{timestamp}.png"
            folder = os.path.join(os.getcwd(), "screenshots")

            if not os.path.exists(folder):
                os.makedirs(folder)

            path = os.path.join(folder, file_name)

            # Screenshot logic
            if loc:
                loc.screenshot(path=path)
            else:
                self.page.screenshot(path=path)

            # Extent report logging
            print(f"Screenshot: {path}")

            # Remove highlight
            if loc:
                self.page.locator(element).evaluate(
                    "el => el.style.border=''"
                )

            return path

        except Exception as e:
            print(
                f"Playwright screenshot failed: {str(e)}"
            )
            return None

    def is_enabled(self, locator) -> bool:
        try:
            return self.page.locator(locator).is_enabled()
        except Exception:
            return False

    def is_displayed(self, locator: str) -> bool:
        return self.page.locator(locator).is_visible()

    def switch_window(self, page, context):
        self.page = self.context.new_page()

    def open_new_tab(self):
        try:
            new_page = self.context.new_page()
            self.page = new_page
            new_page.bring_to_front()
            return True
        except Exception as e:
            print(f"Error opening new tab: {e}")
            return False

#------------Clear Field-----------
    def clear_field(self, locator):
        try:
            element = self.page.locator(locator).first
            element.click()
            element.press("Control+a")
            element.press("Delete")
            return True
        except Exception:
            return False

#-------------Tab Action-------------
    def click_tab(self):
        self.page.keyboard.press("Tab")

    def clear_field_with_limit(self, locator,limit):
        try:
            for i in range(limit):
                element = self.page.locator(locator).first
                element.click()
                element.press("Backspace")
            return True
        except Exception:
            return False

#----------------Wait 1 second-------
    def wait_a_second(self):
        self.page.wait_for_timeout(1000)

#----------- javascript click-----------

    def js_click(self, locator):
        try:
            element = self.page.locator(locator)
            try:
                element.click(timeout=5000)
            except:
                element.evaluate("el => el.click()")
            return True
        except Exception:
            return False

#------- get Text-------
    def get_text(self, locator):
        try:
            element = self.page.locator(locator)
            element.wait_for(state="visible", timeout=60000)

            text = element.inner_text().strip()

            print(f"Get text from {locator}: '{text}'")  # Replace with logger if needed
            return text

        except Exception as e:
            print(f"Error getting text from {locator}: {e}")
            return None


    def mouse_hover(self, locator):
        try:
            self.page.locator(locator).hover()
            return True
        except Exception:
            return False


    def add_time_to_short(self):
        try:
            return datetime.now().strftime("%d%m%y_%H%M")
        except Exception:
            raise

    def wait_for_scroll(self):
        self.page.wait_for_load_state("domcontentloaded")


    def is_selected(self, locator):
        try:
            checked = self.actions.get_attribute(locator, "checked")
            return checked is not None and (checked == "true" or checked == "checked")
        except Exception:
            return False


    def get_input_value(self, element):
        return self.page.locator(element).input_value()

    # Switch to Frame
    def switch_to_frame(self, frame_locator):
        try:
            iframe_element = self.page.locator(frame_locator).first.element_handle()

            if iframe_element is None:
                return False

            frame = iframe_element.content_frame()

            if frame is None:
                return False
            self.current_frame = frame
            return True

        except Exception:
            return False

        except Exception:
                return False

    def enter_value_frame(self, locator, value):
        try:
            frame = self.current_frame
            if frame is None:
                return False

            frame.locator(locator).fill(value)
            return True

        except Exception as e:
            print(f"Unable to enter value in frame: {e}")
            return False

    def switch_to_default_content(self):
        try:
            self.current_frame = None
            return True
        except Exception as e:
            print(f"Unable to switch to default content: {e}")
            return False

    def get_text_frame(self, locator):
        try:
            frame = self.current_frame
            if frame is None:
                return ""

            text = frame.locator(locator).text_content()
            return text.strip() if text else ""

        except Exception as e:
            print(f"Unable to get text from frame: {e}")
            return ""

    def select_frame_text(self, locator):
        try:
            self.click_tab()
            frame = self.current_frame

            if frame is None:
                return False

            frame.locator(locator).press("Control+A")
            return True

        except Exception as e:
            print(f"Unable to select text in frame: {e}")
            return False


    def add_time_to_short(self):
        try:
            return datetime.now().strftime("%d%m%y_%H%M")
        except Exception:
            raise

    def wait_for_scroll(self):
        self.page.wait_for_load_state("domcontentloaded")

    def clear_field(self, locator):
        self.page.locator(locator).fill("")


    def validate_text_in_preview(self, expected_text, locator, field_name):
        try:
            if not expected_text:
                print(f"[ERROR] Expected {field_name} text is empty or None")
                return False

            self.actions.wait_for_element(locator)
            actual_text = self.page.locator(locator).first.inner_text().strip()

            expected = " ".join(expected_text.split())
            actual = " ".join(actual_text.split())

            print(f"[INFO] Expected {field_name} Preview → {expected}")
            print(f"[INFO] Actual {field_name} Preview → {actual}")

            if expected != actual:
                print(f"[FAIL] {field_name} preview mismatch")
                return False

            print(f"[PASS] {field_name} preview validated successfully")
            return True

        except Exception as e:
            print(f"[ERROR] Failed to validate {field_name} preview → {e}")
            return False

    def get_inner_text(self, locator):
        try:
            ele = self.page.locator(locator).first
            ele.wait_for(state="visible", timeout=10000)
            return ele.inner_text()
        except Exception as e:
            print(f"[ERROR] Unable to get inner text → {e}")
            return ""

    def get_text_content(self, locator):
        try:
            ele = self.page.locator(locator).first
            ele.wait_for(state="attached", timeout=10000)
            text = ele.text_content()
            return text.strip() if text else ""
        except Exception as e:
            print(f"[ERROR] Unable to get text content → {e}")
            return ""

    def scroll_to_top(self) -> bool:
        try:
            self.page.evaluate("window.scrollTo(0, 0)")
            return True
        except Exception:
            return False

    def wait_half_second(self):
        time.sleep(0.5)

    def refresh(self):
        self.page.reload()
        print("Page Refreshed")

    def get_current_window_handle(self) -> str:
        context = self.page.context
        return f"PAGE_{context.pages.index(self.page)}"

    def get_all_window_handles(self) -> list[str]:
        handles = []

        pages = self.page.context.pages

        for i in range(len(pages)):
            handles.append(f"PAGE_{i}")

        return handles

    def open_new_tab(self) -> bool:
        try:
            new_page = self.page.context.new_page()

            self.page = new_page

            new_page.bring_to_front()

            print("Opened new tab")
            return True

        except Exception as e:
            print(f"Error opening new tab: {e}")
            return False

    def switch_window(self):
        try:
            pages = self.page.context.pages
            if len(pages) < 2:
                print("No additional window to switch")
                return
            last_opened = pages[-1]
            self.page = last_opened
            last_opened.bring_to_front()
            print("Switched to last opened window")
        except Exception as e:
            print(f"Error switching window: {e}")

    def double_click(self, locator) -> bool:
        try:
            self.page.locator(locator).dblclick()
            return True
        except Exception as e:
            print(f"Double Click failed : {str(e)}")
            return False

    def close_all_other_windows(self) -> bool:
        try:
            context = self.context
            pages = context.pages

            if not pages:
                return False

            parent = pages[0]

            # Close all other tabs
            for page in pages[:]:  # copy list to avoid modification issues
                if page != parent:
                    page.close()

            # # Set parent as active
            # self.set_page(parent)  # your custom method
            # self.update_page(parent)  # equivalent of super.updatePage()

            parent.bring_to_front()

            print("[INFO] Closed all other windows")

            return True

        except Exception as e:
            print(f"[ERROR] close_all_other_windows: {e}")
            return False



    def switch_to_window(self, window_handle: str) -> bool:
        try:
            index = int(window_handle.replace("PAGE_", ""))
            return self.switch_to_window_by_index(index)
        except Exception:
            print(f"Invalid window handle: {window_handle}")
            return False

    def switch_to_window_by_index(self, index: int) -> bool:
        try:
            pages = self.page.context.pages

            if index < 0 or index >= len(pages):
                return False

            target = pages[index]

            # ✅ Update page reference
            self.page = target

            # ✅ Sync actions
            self.page = target

            target.bring_to_front()

            return True

        except Exception:
            return False

    def switch_to_window_by_url_index(self, url: str, index: int) -> bool:
        try:
            pages = self.page.context.pages

            # Filter pages by URL
            filtered_pages = [p for p in pages if url in p.url]

            # Same index validation like your method
            if index < 0 or index >= len(filtered_pages):
                return False

            target = filtered_pages[index]

            # ✅ Update page reference
            self.page = target

            # ✅ Bring to front
            target.bring_to_front()

            return True

        except Exception:
            return False

    def get_current_date(self, fmt: str) -> str:
        try:
            date = datetime.now().strftime(fmt)
            print(f"[INFO] Current date: {date}")
            return date
        except Exception as e:
            print(f"[ERROR] Failed to get current date: {e}")
            raise

    def normalize_text(self, input_text: str) -> str:
        if input_text is None:
            return ""

        return re.sub(
            r"\s+",
            " ",
            input_text.replace("\u00A0", " ")
        ).strip()


    def ellipsis(self):
        return '\u2026'


    def download_file(self, locator):
        try:
            download_dir = Path(os.getcwd()) / "data" / "downloaded_file"
            download_dir.mkdir(parents=True, exist_ok=True)
            print(f"📁 Download directory: {download_dir}")
            element = self.page.locator(locator)
            element.wait_for(state="visible", timeout=10000)
            with self.page.expect_download(timeout=20000) as download_info:
                element.click(force=True)
            download = download_info.value
            print("📥 Download triggered:", download.suggested_filename)

            file_name = download.suggested_filename or f"download_{int(time.time())}.csv"
            file_path = download_dir / file_name
            download.save_as(str(file_path))
            for _ in range(15):
                if file_path.exists():
                    break
                time.sleep(0.5)
            if not file_path.exists():
                raise Exception("❌ File not saved!")
            print(f"✅ File saved: {file_path}")
            return file_path
        except Exception as e:
            print(f"❌ Download failed: {str(e)}")
            return None

    def file_handles(self):
        csv_data = []

        try:
            path = Path(os.getcwd()) / "data" / "downloaded_file"
            files = list(path.iterdir()) if path.exists() else []

            if not files:
                print("No files found in directory")
                return csv_data
            for file in files:
                file_name = file.name
                if file.exists() and file.suffix.lower() in [".csv", ".txt"]:

                    print(f"Processing file: {file_name}")

                    try:
                        try:
                            with open(file, "r", encoding="utf-16") as reader:
                                header_line = reader.readline()

                                if header_line and header_line.strip():
                                    print("Using OLD logic (utf-16 + tab)")

                                    headers = header_line.strip().split("\t")

                                    for line in reader:
                                        if not line.strip():
                                            continue

                                        values = line.strip().split("\t")
                                        row_map = {}

                                        for i in range(min(len(headers), len(values))):
                                            row_map[headers[i].strip()] = values[i].strip()

                                        csv_data.append(row_map)

                                    continue  # ✅ success → skip new logic

                        except Exception as e:
                            print(f"Old logic failed: {e}")

                        try:
                            try:
                                reader = open(file, "r", encoding="utf-8")
                            except:
                                reader = open(file, "r", encoding="latin-1")

                            header_line = reader.readline()

                            if not header_line or not header_line.strip():
                                print("Empty header, skipping file")
                                reader.close()
                                continue

                            print("Using NEW logic (auto detect)")

                            delimiter = "," if "," in header_line else "\t"
                            headers = header_line.strip().split(delimiter)

                            for line in reader:
                                if not line.strip():
                                    continue

                                values = line.strip().split(delimiter)
                                row_map = {}

                                for i in range(min(len(headers), len(values))):
                                    row_map[headers[i].strip()] = values[i].strip()

                                csv_data.append(row_map)

                            reader.close()

                        except Exception as e:
                            print(f"New logic failed: {e}")

                    except Exception as e:
                        print(f"{file_name} Error: {e}")

                    finally:
                        try:
                            if file.exists():
                                file.unlink()
                                print(f"Deleted file: {file_name}")
                        except Exception as e:
                            print(f"Delete error: {e}")

            return csv_data

        except Exception as e:
            print(f"Error in file_handles: {e}")
            return csv_data

    def switch_to_parent_window(self):
        try:
            pages = self.page.context.pages
            self.page = pages[0]
            self.page.bring_to_front()
            return True
        except Exception as e:
            print(f"Error switching to parent window: {e}")
            return False

    def sendValue(self, locator, value: str) -> bool:
        try:
            self.resolveLocator(locator).fill(value)
            return True
        except Exception:
            return False

    def child_window_close_index(self, index: int) -> bool:
        try:
            pages = self.context.pages

            if index <= 0 or index >= len(pages):
                print(f"Invalid child window index: {index}")
                return False

            target = pages[index]
            target.close()

            parent = self.context.pages[0]
            self.page = parent
            parent.bring_to_front()

            print(f"Closed child window at index: {index}")
            return True

        except Exception as e:
            print(f"Error closing child window at index {index}: {e}")
            return False

    def drag_list_audience_to_canvas(self):
        try:
            page = self.page
            self.wait_a_second()
            # Locate drag element
            drag_element = self.locator("//i[contains(@class,'user-segments')]")
            source_box = drag_element.bounding_box()

            if not source_box:
                print("Drag element not found")
                return False

            # Move mouse to center of drag element
            page.mouse.move(
                source_box["x"] + source_box["width"] / 2,
                source_box["y"] + source_box["height"] / 2,
                steps=17
            )
            page.mouse.down()

            # Wait before moving to canvas
            page.wait_for_timeout(1000)

            # Hover on canvas
            page.hover("#main-canvas")

            # Locate drop element
            drop_element = page.locator("//div[contains(@class,'placeholder-text res-mdc')]")

            # Wait until visible
            drop_element.wait_for(state="visible", timeout=5000)

            if drop_element.is_visible():
                drop_box = drop_element.bounding_box()

                if not drop_box:
                    print("Drop element box not found")
                    return False

                # Move to drop target center
                page.mouse.move(
                    drop_box["x"] + drop_box["width"] / 2,
                    drop_box["y"] + drop_box["height"] / 2,
                    steps=17
                )

                page.wait_for_timeout(1000)

                # Release mouse (drop)
                page.mouse.up()

                # Screenshot (assuming method exists)

                return True
            else:
                print("Drop element not visible within timeout")
                return False

        except Exception as e:
            print(f"Error occurred: {e}")
            return False

    def close_current_window(self) -> bool:
        if len(self.context.pages) == 0:
            return False
        current = self.page
        current.close()
        fallback = self.context.pages[0]
        fallback.bring_to_front()
        return True
