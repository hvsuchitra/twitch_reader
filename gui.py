import sys
import os
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QApplication, QWidget, QToolTip, QPushButton, QGridLayout, QLineEdit, QLabel
from PyQt5.QtGui import QFont

from utils import get_chat, get_chat_contents, text_to_speech

os.chdir(sys.path[0])  # Change Current Directory to the location of gui.py


class GetChatThread(QThread):
    """Subclass of `QThread` that is used to call the `get_chat` function
    
    Attributes:
        signal (PyQT5.QtCore.pyqtSignal): Signal that is used to communicate between objects
    """

    signal = pyqtSignal('PyQt_PyObject')

    def run(self):
        """Method is invoked when the thread is started
        This in turn starts the `get_chat` function in a new thread
        """
        self.signal.emit(get_chat(self.channel_name))


class GetChatContentsThread(QThread):
    """Subclass of `QThread` that is used to call the `get_chat_contents` function
    
    Attributes:
        signal (PyQT5.QtCore.pyqtSignal): Signal that is used to communicate between objects
    """

    signal = pyqtSignal('PyQt_PyObject')

    def __init__(self, path, from_):
        """Constructor
        
        Args:
            path (str): Name of the current channel
            from_ (str): Name of the button that invoked this function
        """
        self.path = path
        self.from_ = from_
        super().__init__()

    def run(self):
        """Method is invoked when the thread is started
        This in turn starts the `get_chat_contents` function in a new thread
        """
        self.signal.emit(get_chat_contents(self.path, self.from_))


class TTSThread(QThread):
    """Subclass of `QThread` that is used to call the `text_to_speech` function
    
    Attributes:
        signal (PyQT5.QtCore.pyqtSignal): Signal that is used to communicate between objects
    """

    signal = pyqtSignal('PyQt_PyObject')

    def __init__(self, data):
        """Constructor
        
        Args:
            data (str): Chat message that is to be converted to speech
        """
        self.data = data
        super().__init__()

    def run(self):
        """Method is invoked when the thread is started
        This in turn starts the `text_to_speech` function in a new thread
        """
        self.signal.emit(text_to_speech(self.data))


class HomeScreen(QWidget):

    """The Main GUI Window for the application, inherited from `QWidget`
    
    Attributes:
        channel_name_text_field (QLineEdit): Text Field for Channel Name
        chat_content_label (QLabel): Label for Channel Name Text Field
        get_chat_contents_thread (QThread): Thread object used to call `get_chat_contents`
        get_chat_thread (QThread): Thread object used to call `get_chat`
        grid (QGridLayout): Grid Layout for the entire GUI
        mention_button (QPushButton): Button that reads any chats that has mentioned the name of the channel (`eg: @channel_name`)
        read_last_button (QPushButton): Button that reads the last chat message from the IRC stream
        read_random_button (QPushButton): Button that reads any random message from the IRC stream
        start_chat_button (QPushButton): Starts a thread that establishes a socket connection and logs the chats
        tts_thread (QThread): Thread object used to call `text_to_speech`
    """
    
    def __init__(self):
        """Setup the GUI Widgets and Button"""
        super().__init__()

        Path('logs').mkdir(exist_ok=True)

        QToolTip.setFont(QFont('SansSerif', 10))
        self.setGeometry(300, 300, 300, 220)
        self.setWindowTitle('TwitchReader')

        self.grid = QGridLayout()
        self.grid.setSpacing(10)
        self.setLayout(self.grid)

        self.channel_name_text_field = QLineEdit(self)
        self.channel_name_text_field.setPlaceholderText('Channel Name')
        self.grid.addWidget(self.channel_name_text_field, 0, 0)
        self.channel_name_text_field.textEdited.connect(self.validate)

        self.start_chat_button = QPushButton('Start', self)
        self.grid.addWidget(self.start_chat_button, 0, 1)
        self.start_chat_button.setEnabled(False)
        self.start_chat_button.clicked.connect(self.start_chat)
        self.get_chat_thread = GetChatThread()

        self.chat_content_label = QLabel(self)
        self.chat_content_label.setWordWrap(True)
        self.grid.addWidget(self.chat_content_label, 1, 0, 1, 2)

        self.read_random_button = QPushButton('Read Random', self)
        self.grid.addWidget(self.read_random_button, 2, 0)
        self.read_random_button.setEnabled(False)
        self.read_random_button.clicked.connect(self.start_text_to_speech)

        self.read_last_button = QPushButton('Read Last', self)
        self.grid.addWidget(self.read_last_button, 2, 1)
        self.read_last_button.setEnabled(False)
        self.read_last_button.clicked.connect(self.start_text_to_speech)

        self.mention_button = QPushButton('@ me', self)
        self.grid.addWidget(self.mention_button, 3, 0, 1, 2)
        self.mention_button.setEnabled(False)
        self.mention_button.clicked.connect(self.start_text_to_speech)

        self.show()

    def validate(self):
        """Helper method to enable the "Start" (`start_chat_button`) button"""
        self.start_chat_button.setEnabled(bool(self.channel_name_text_field.text().strip()))

    def start_chat(self):
        """Helper method that calls the actual method that connects to the IRC stream using a socket
        Disables the "Start" button after it is started
        Enables the "Read Random", "Read Last" and "@ me" button after it is started
        This prevents the user from trying to start more than one thread for logging in the same GUI
        Start the GUI app as a different process to enable logging across multiple channels
        """
        self.start_chat_button.setEnabled(False)
        self.channel_name_text_field.setDisabled(True)
        toggle = (self.read_random_button, self.read_last_button, self.mention_button)
        for button in toggle:
            getattr(button, 'setEnabled')(True)
        self.get_chat_thread.channel_name = self.channel_name_text_field.text().strip()
        self.get_chat_thread.start()

    def start_text_to_speech(self):
        """Helper method that retrieves the chat message that is to be converted to speech"""
        self.toggle_button('stub', False)
        self.get_chat_contents_thread = GetChatContentsThread(self.get_chat_thread.channel_name, self.sender().text())
        self.get_chat_contents_thread.signal.connect(self.stop_text_to_speech)
        self.get_chat_contents_thread.start()

    def stop_text_to_speech(self, chat):
        """Helper method that converts the chat message to speech
        Calls the `text_to_speech` method in a thread
        
        Args:
            chat (dict): Dictionary of the chat message that is to be converted to speech
        """
        state, chat_to_read = chat
        if not state:
            self.chat_content_label.setText(chat_to_read)
            self.toggle_button(
                'stub')  # is it better to just enable the buttons here instead of passing a stub signal to a method?
        else:
            data = f"{chat_to_read['username']} says {chat_to_read['comment']}"
            self.chat_content_label.setText(data)
            self.tts_thread = TTSThread(data)
            self.tts_thread.signal.connect(self.toggle_button)
            self.tts_thread.start()

    def toggle_button(self, signal, state=True):
        """Used to toggle the state of buttons
        
        Args:
            signal (str): stub argument, no actual use
            state (bool, optional): State to toggle the buttonsm `True` = enable, `False` = disable
        """
        self.read_random_button.setEnabled(state)
        self.read_last_button.setEnabled(state)
        self.mention_button.setEnabled(state)


app = QApplication(sys.argv)
ex = HomeScreen()
app.exec_()
