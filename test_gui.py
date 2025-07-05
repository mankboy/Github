import tkinter
from tkinter import messagebox

# This simple script tries to do one thing: show a message box.
print("Attempting to create a Tkinter window...")
try:
    root = tkinter.Tk()
    root.withdraw() # Hide the main empty window
    messagebox.showinfo("GUI Test", "Tkinter is working correctly!")
    print("Test successful. Message box was shown.")
except Exception as e:
    print(f"An error occurred: {e}")