from abc import ABC, abstractmethod


class WebActions(ABC):

    @abstractmethod
    def navigate(self, url):
        pass

    @abstractmethod
    def click_element(self, locator):
        pass

    @abstractmethod
    def enter_value(self, locator, value):
        pass

    @abstractmethod
    def get_value(self, locator):
        pass

    @abstractmethod
    def get_attribute(self, locator, attribute):
        pass