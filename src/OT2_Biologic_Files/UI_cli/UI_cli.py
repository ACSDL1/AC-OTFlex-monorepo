import OT_Manager

def getNumberInput(fieldName:str, min:int = 1, max:int = 999, default:int = 1) -> int:
    """
    Prompts the user to enter a number within a specified range, with an option to use a default value.
    
    Args:
        fieldName (str): The name of the field being requested (for display purposes).
        min (int): The minimum allowable value (inclusive). Default is 1.
        max (int): The maximum allowable value (inclusive). Default is 999.
        default (int): The default value to use if the user presses Enter. Default is 1.
    
    Returns:
        int: The validated user input or the default value.
    """
    print("==========================")
    print(f"Select a {fieldName} ({min}-{max}):")
    
    inputtedAns = 0  # Stores the validated input
    while True:
        user_input = input(f"Enter {fieldName} (or press Enter for {default}): ").strip()
        
        if not user_input:  # If no input, use the default value
            inputtedAns = default
        elif user_input.isdigit() and min <= int(user_input) <= max:  # Validate input is within range
            inputtedAns = int(user_input)
        else:  # Handle invalid input
            print(f"Invalid input. Please enter a number between {min} and {max}.")
            continue
        
        break  # Exit the loop if input is valid
    
    print(f"{fieldName} selected: {inputtedAns}")
    return inputtedAns

def getAddressInput(fieldName:str, numRows:int, numCols:int, default:str = 'A1') -> str:
    print("==========================")
    print(f"Select a {fieldName}:")
    
    inputtedAns = ''
    while True:
        user_input = input(f"Enter {fieldName} (or press Enter for '{default}'): ").strip()
        
        if not user_input:  # If no input, use the default value
            inputtedAns = default
        elif OT_Manager.verifyAddress(user_input, numCols, numRows):  # Validate input is within range
            inputtedAns = user_input
        else:  # Handle invalid input
            print(f"Invalid input. Please enter an Opentron address (Like A1, B2, ...).")
            continue
        
        break  # Exit the loop if input is valid
    
    print(f"{fieldName} set: {inputtedAns}")
    return inputtedAns