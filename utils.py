import re
import socket
import logging
from logging.handlers import RotatingFileHandler
from random import shuffle
from configparser import ConfigParser

import pythoncom
from win32com.client import Dispatch

# Set Log Format
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s-%(message)s', datefmt='%Y-%m-%d_%H:%M:%S')


def __get_path(channel):
    """Internal Function to get the path of the current log file
    
    Args:
        channel (str): Name of the channel to connect in the IRC stream
    
    Returns:
        str: log file location for the current channel
    """
    return f'logs/#{channel}.log'


def __initialize_blacklist(entry):
    """Helper function used to create blacklist entries
    
    Args:
        entry (str): Entry to read from the "blacklist" section in the app.conf file
    
    Returns:
        generator: Values that are defined in the "blacklist" section for the entry specified
        tuple: if there are no values for the entry
    """
    return (x.strip().casefold() for x in val.split(',')) if (
        val := config_parser.get('blacklist', entry, fallback=None)) else tuple()


# Config File Initialization
config_parser = ConfigParser()
config_parser.read('app.conf')

# Get Values needed for the app to function
token = config_parser.get('connection', 'token')
server = config_parser.get('connection', 'server')
port = config_parser.getint('connection', 'port')
nickname = config_parser.get('connection', 'nickname')
random_limit = config_parser.getint('value', 'random_limit')

max_bytes = (t if (t := config_parser.getfloat('value', 'log_size_megabytes')) else 1) * 2 ** 20
backup_count = t if (t := config_parser.getint('value', 'log_backup_count')) >= 1 else 1

# Blacklist configuration
blacklisted_users = set(__initialize_blacklist('users'))
prefixes_not_allowed = tuple(__initialize_blacklist('begin_with'))
suffixes_not_allowed = tuple(__initialize_blacklist('end_with'))


def get_chat(channel):
    """Helper function that runs in a separate thread
    Reads and logs data from an IRC stream
    Log data is printed to stdout and to dumped to a file
    Rotating Log File Handler is used to maintain old logs

    
    Args:
        channel (str): Name of the channel to connect in the IRC stream
    """

    # implement a rotating log handler
    logger = logging.getLogger(channel)
    rotating_log_file_handler = RotatingFileHandler(__get_path(channel), encoding='utf-8', mode='w', maxBytes=max_bytes,
                                                    backupCount=backup_count)
    rotating_log_file_handler.setLevel(logging.DEBUG)
    log_formatter = logging.Formatter('%(asctime)s-%(message)s', datefmt='%Y-%m-%d_%H:%M:%S')
    rotating_log_file_handler.setFormatter(log_formatter)
    logger.addHandler(rotating_log_file_handler)

    with socket.socket() as sock:
        # connect to IRC stream by sending appropriate IRC commands
        sock.connect((server, port))
        sock.send(f'PASS {token}\n'.encode('utf-8'))  # token
        sock.send(f'NICK {nickname}\n'.encode('utf-8'))  # twitch user name
        sock.send(f'JOIN {f"#{channel}"}\n'.encode('utf-8'))  # join the IRC stream for the channel entered
        idx = -1
        while data := sock.recv(2048):  # keep reading as long there are bytes received
            idx += 1
            data = data.decode('utf-8')
            if data.startswith('PING'):  # IRC server sends a PING periodically
                sock.send('PONG :tmi.twitch.tv\n'.encode('utf-8'))  # respond with PONG to maintain connection
                continue
            if idx < 2:
                continue  # the first 3 responses are welcome messages form the IRC and will not be logged
            logger.debug(data)


def __blacklist_filter(chats, rand_order):
    """Blacklists chats based on the following condtions
    username should not be in `blacklisted_users`
    chat message (`chat['comment']`) should not contain blacklisted prefixes or suffixes
    
    Args:
        chats (list): List of chat messages dicts extracted from the current log handler
        rand_order (list): List of indices to read chat message from
    
    Returns:
        tuple: Tuple of bool, str
        if `True` then `text_to_speech` is called, if `False`, `text_to_speech` is not called
    """
    while rand_order:
        # Checks for the condtions mentioned above
        if ((chat := chats[rand_order.pop()])['username'].casefold() not in blacklisted_users) and (
                not (chat_comment := chat['comment'].strip().casefold()).startswith(
                    prefixes_not_allowed) or not chat_comment.endswith(suffixes_not_allowed)):
            return True, chat
    return False, f'Content in the last {random_limit} chats is blacklisted based on message or username'


def get_chat_contents(channel, from_):
    """Function that runs in a thread that is used to get the message to be converted to speech
    
    Args:
        channel (str): Name of the current channel
        from_ (str): Name of the button that invoked this function
    
    Returns:
        tuple: Tuple of bool, string
    """
    # benchmark and check
    # "slicing up to random_limit and then from a random sorted seq" with "random choice from whole list"
    with open(__get_path(channel), encoding='utf-8') as chat_log:  # open the log file
        # form a `chats` list that is a dictionary of different chat messages gathered from the IRC stream
        chats = [i.groupdict() for i in re.finditer(r":(?P<username>\w*)!.*#\w*.*?:(?P<comment>.*)", chat_log.read())]
        reduced_range = min(random_limit, len(chats))
        # keep only the last `random_limit` elements or all elements if length is less than `random_limit`
        chats = chats[-reduced_range:]
    if not chats:
        return False, 'No chats to retrieve'
    rand_order = [*range(-reduced_range, 0)]

    # use `from_` to check the button that invoked this function and branch accordingly
    if from_ == 'Read Random':
        shuffle(rand_order)
        return __blacklist_filter(chats, rand_order)
    elif from_ == 'Read Last':
        return __blacklist_filter(chats, rand_order)
    elif from_ == '@ me':
        case_folded_channel = f'@{channel.casefold()}'
        chats = [chat for chat in chats if (chat_comment := chat['comment'].strip().casefold()).startswith(
            case_folded_channel) or chat_comment.endswith(case_folded_channel)]
        rand_order = [*range(-len(chats), 0)]
        return __blacklist_filter(chats, rand_order) if chats else (
            False, f'No one has mentioned you in the last {random_limit} chats yet')


def text_to_speech(text):
    """Function that runs in a thread and converts `text` into speech
    
    Args:
        text (str): Message to be converted to speech
    """
    pythoncom.CoInitialize()
    speaker = Dispatch('SAPI.SpVoice')  # SPVoice object that enables tts
    voice = speaker.GetVoices()[1]  # get the voice type
    speaker.Voice  # initialize `Voice` property
    speaker.SetVoice(voice)  # set the voice type to use
    speaker.Speak(text)  # tts
