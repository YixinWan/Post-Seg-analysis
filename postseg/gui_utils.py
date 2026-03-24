import tkinter as tk
from tkinter import filedialog

def select_image_file():
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(
        title='选择图片',
        filetypes=[('Image Files', '*.png;*.jpg;*.jpeg;*.bmp;*.tiff;*.tif')]
    )
    root.destroy()
    return file_path
