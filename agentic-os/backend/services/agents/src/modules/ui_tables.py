# modules/ui_tables.py

from modules.ui_table_turns import print_turns_table
from modules.ui_table_api import print_api_table
from modules.ui_table_deletions import print_deletions_table
from modules.ui_table_agents import print_agents_table, print_call_stack_table

def print_all_tables():
    """
    Calls each submodule's table-print function in sequence.
    """

    print()
    print_deletions_table()
    print()
    print_agents_table()
    print()
    print_call_stack_table()
    print()
    print_api_table()
    print()
    print_turns_table()
    print()

if __name__ == "__main__":
    print_all_tables()
