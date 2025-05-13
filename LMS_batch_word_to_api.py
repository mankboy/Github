#!/usr/bin/env python3
# LMS_batch_word_to_api.py
# Process Word documents with AnythingLLM API

import os
import sys
import time
import json
import queue
import logging
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import docx
import requests
import numpy as np
import cv2
import pyautogui
import keyboard
from PIL import Image
from fpdf import FPDF
import psutil
import GPUtil
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('lms_processor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Global variables
API_REQUESTS = {
    'total_sent': 0,
    'successful': 0,
    'failed': 0,
    'last_error': None
}

# Configuration file path
CONFIG_FILE = 'lms_config.json'

def load_config():
    """Load configuration from file"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading config: {str(e)}")
    return {
        "api_endpoint": "http://localhost:3001/api/chat",
        "model": "gpt-3.5-turbo",
        "api_timeout": "150",
        "last_input_dir": "",
        "last_output_dir": ""
    }

def save_config(config):
    """Save configuration to file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving config: {str(e)}")

# ... existing code ...