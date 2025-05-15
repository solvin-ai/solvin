# modules/ui_tables_common.py

"""
modules/ui_tables_common.py

Common helpers for constructing and printing Rich tables. This module provides:
  • get_console: Returns a Rich Console instance.
  • create_rich_table: Constructs a configured Rich Table.
  • smart_truncate_text: Truncates text intelligently by preserving the beginning and end.
  • sanitize_text: Sanitizes text by replacing newlines, tabs, and carriage returns with a space.
  • compute_dynamic_column_width: Calculates the available width for a dynamic column given the fixed columns.
  • add_rows_with_separator: Adds rows to a table and inserts a horizontal separator at specified intervals.

Note: Ensure that nothing in this module imports from itself to avoid circular import issues.
"""

from rich.console import Console
from rich.table import Table
import re

def get_console():
    """
    Returns a Rich Console instance.
    """
    return Console()

def create_rich_table(title, columns_config, show_lines=False, expand=True, compact=False, last_column_expand=True):
    """
    Creates and returns a Rich Table based on the provided configuration.
    
    Parameters:
      title          - The table title.
      columns_config - A list of dictionaries, where each dictionary describes a column.
                       Each dict can include:
                           • "header": The column header text.
                           • "justify": One of "left", "center", or "right".
                           • "overflow": Overflow strategy (e.g. "ellipsis", "fold").
                           • "no_wrap": Boolean flag to control wrapping.
      show_lines         - If True, row separator lines are shown.
      expand             - If True, table will take up full console width.
      compact            - If True, uses a compact layout.
      last_column_expand - If True, the last column automatically expands.
    
    Returns:
      A configured rich.table.Table instance.
    """
    table = Table(title=title, show_lines=show_lines, expand=expand, padding=(0, 1), collapse_padding=compact)
    for col in columns_config:
        table.add_column(
            col.get("header", ""),
            justify=col.get("justify", "left"),
            no_wrap=col.get("no_wrap", False),
            overflow=col.get("overflow", "ellipsis")
        )
    return table

def smart_truncate_text(text, max_width, ellipsis="…"):
    """
    Smartly truncates text to a specified max_width by retaining the beginning and end,
    inserting an ellipsis in the middle if necessary.
    
    Parameters:
      text      - The text to truncate.
      max_width - Maximum allowed width (in characters).
      ellipsis  - The ellipsis string to use (default is "…").
      
    Returns:
      The original text if its length is less than or equal to max_width,
      otherwise a truncated version.
      
    Example:
      smart_truncate_text("Very long filename_example.txt", 15)
      might yield: "Very…ample.txt"
    """
    if not isinstance(text, str):
        text = str(text)
    if len(text) <= max_width:
        return text
    if max_width <= len(ellipsis):
        return text[:max_width]
    part = (max_width - len(ellipsis)) // 2
    return text[:part] + ellipsis + text[-part:]

def sanitize_text(text):
    """
    Sanitizes the input text by replacing newline, carriage return, and tab characters with a single space.
    Also collapses multiple spaces into one and strips leading/trailing whitespace.
    
    Parameters:
      text - The text to sanitize.
      
    Returns:
      A sanitized version of the text.
    """
    if not isinstance(text, str):
        text = str(text)
    sanitized = re.sub(r'[\n\r\t]+', ' ', text)
    sanitized = re.sub(r' +', ' ', sanitized)
    return sanitized.strip()

def compute_dynamic_column_width(console, fixed_headers, rows, fixed_count, layout_extra=None, default_min=10):
    """
    Computes the available width for a dynamic column.
    
    Parameters:
      console       - A Rich Console object (using console.size.width).
      fixed_headers - A list of header texts for the fixed columns.
      rows          - A list of rows; each row is a list of cell strings.
      fixed_count   - Number of fixed columns.
      layout_extra  - (Optional) Extra characters to account for padding, borders and table lines.
                      If not provided, it is computed as 3 * (fixed_count + 1) + 1.
      default_min   - (Optional) Minimum allowed width for the dynamic column (default is 10).
    
    Returns:
      An integer representing the available width (in characters) for the dynamic column.
      
    The layout_extra calculation now accounts for:
     • 2 extra spaces (padding) per column, and
     • Vertical borders (one extra per column plus one extra on the left)
     Totaling: (2 * total_columns) + (total_columns + 1) = 3 * total_columns + 1.
    """
    fixed_widths = []
    for i in range(fixed_count):
        header_text = fixed_headers[i]
        max_width = len(header_text)
        for row in rows:
            cell = row[i] or ""
            cell_length = len(str(cell))
            if cell_length > max_width:
                max_width = cell_length
        fixed_widths.append(max_width)
    
    total_fixed = sum(fixed_widths)
    
    if layout_extra is None:
        total_columns = fixed_count + 1  # fixed columns plus one dynamic column.
        layout_extra = 3 * total_columns + 1

    available = console.size.width - (total_fixed + layout_extra)
    return available if available > default_min else default_min

def add_rows_with_separator(table, rows, separator_interval=2):
    """
    Adds rows to the provided Rich Table, inserting a horizontal separator every separator_interval rows.
    
    The separator is inserted using table.add_section(), which creates a line break between sections.
    
    Parameters:
      table              - The Rich Table object.
      rows               - A list of rows (each row is a list of cell values).
      separator_interval - Number of rows after which a separator is added.
    """
    for index, row in enumerate(rows, start=1):
        table.add_row(*row)
        if index % separator_interval == 0 and index < len(rows):
            table.add_section()
