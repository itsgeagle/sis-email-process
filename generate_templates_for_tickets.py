import warnings
warnings.warn(
    "This script is deprecated. Use 'python app.py' instead.",
    DeprecationWarning,
    stacklevel=1,
)

import os
import shutil
from generate_template import generate_template

# Read the list of SISRP ticket IDs from tickets.txt
with open('inputs/tickets.txt', 'r') as file:
    ticket_ids = [line.strip() for line in file if line.strip()]  # Read and strip each line, skipping empty lines

# Specify the output folder
output_folder = 'filled_templates'

# Clear the folder by deleting all contents
if os.path.exists(output_folder):
    shutil.rmtree(output_folder)  # Remove the folder and all its contents
os.makedirs(output_folder, exist_ok=True)  # Recreate the folder

# Generate templates for each ticket
for ticket_id in ticket_ids:
    generate_template(ticket_id, output_folder)
