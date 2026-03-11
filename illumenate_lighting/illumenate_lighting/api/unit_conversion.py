# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Unit Conversion Utilities

This module provides standardized conversion functions between metric (mm) and
imperial (inches, feet) units used throughout the ilLumenate Lighting system.

The system stores all length values internally in millimeters (mm) for precision
and consistency, but displays and accepts input in inches for the US market.

Conversion Constants:
- 1 inch = 25.4 mm (exact)
- 1 foot = 12 inches = 304.8 mm (exact)

Usage:
    from illumenate_lighting.illumenate_lighting.api.unit_conversion import (
        mm_to_inches,
        inches_to_mm,
        mm_to_feet_inches,
        feet_inches_to_mm,
        format_length_inches,
        format_length_feet_inches,
    )
"""

from typing import Optional, Union

# Exact conversion constants (these are exact by definition)
MM_PER_INCH = 25.4
MM_PER_FOOT = 304.8
INCHES_PER_FOOT = 12


def mm_to_inches(mm: Union[int, float, None], precision: int = 2) -> Optional[float]:
    """
    Convert millimeters to inches.

    Args:
        mm: Length in millimeters
        precision: Number of decimal places to round to (default: 2)

    Returns:
        Length in inches, or None if input is None/0

    Examples:
        >>> mm_to_inches(25.4)
        1.0
        >>> mm_to_inches(1000)
        39.37
        >>> mm_to_inches(304.8)
        12.0
    """
    if mm is None or mm == 0:
        return None
    return round(float(mm) / MM_PER_INCH, precision)


def inches_to_mm(inches: Union[int, float, None], round_to_int: bool = True) -> Optional[Union[int, float]]:
    """
    Convert inches to millimeters.

    Args:
        inches: Length in inches
        round_to_int: If True, round result to nearest integer (default: True)

    Returns:
        Length in millimeters, or None if input is None/0

    Examples:
        >>> inches_to_mm(1)
        25
        >>> inches_to_mm(12)
        305
        >>> inches_to_mm(48)
        1219
    """
    if inches is None or inches == 0:
        return None
    mm = float(inches) * MM_PER_INCH
    if round_to_int:
        return int(round(mm))
    return round(mm, 2)


def mm_to_feet(mm: Union[int, float, None], precision: int = 2) -> Optional[float]:
    """
    Convert millimeters to feet (decimal).

    Args:
        mm: Length in millimeters
        precision: Number of decimal places to round to (default: 2)

    Returns:
        Length in feet (decimal), or None if input is None/0

    Examples:
        >>> mm_to_feet(304.8)
        1.0
        >>> mm_to_feet(1000)
        3.28
    """
    if mm is None or mm == 0:
        return None
    return round(float(mm) / MM_PER_FOOT, precision)


def feet_to_mm(feet: Union[int, float, None], round_to_int: bool = True) -> Optional[Union[int, float]]:
    """
    Convert feet (decimal) to millimeters.

    Args:
        feet: Length in feet
        round_to_int: If True, round result to nearest integer (default: True)

    Returns:
        Length in millimeters, or None if input is None/0

    Examples:
        >>> feet_to_mm(1)
        305
        >>> feet_to_mm(8.5)
        2591
    """
    if feet is None or feet == 0:
        return None
    mm = float(feet) * MM_PER_FOOT
    if round_to_int:
        return int(round(mm))
    return round(mm, 2)


def mm_to_feet_inches(mm: Union[int, float, None]) -> tuple[int, float]:
    """
    Convert millimeters to feet and inches.

    Args:
        mm: Length in millimeters

    Returns:
        Tuple of (feet, inches) where inches is the remainder

    Examples:
        >>> mm_to_feet_inches(1524)
        (5, 0.0)
        >>> mm_to_feet_inches(1000)
        (3, 3.37)
    """
    if mm is None or mm == 0:
        return (0, 0.0)
    
    total_inches = float(mm) / MM_PER_INCH
    feet = int(total_inches // INCHES_PER_FOOT)
    remaining_inches = round(total_inches % INCHES_PER_FOOT, 2)
    
    return (feet, remaining_inches)


def feet_inches_to_mm(
    feet: Union[int, float, None] = 0,
    inches: Union[int, float, None] = 0,
    round_to_int: bool = True
) -> Optional[Union[int, float]]:
    """
    Convert feet and inches to millimeters.

    Args:
        feet: Feet component
        inches: Inches component
        round_to_int: If True, round result to nearest integer (default: True)

    Returns:
        Length in millimeters, or None if both inputs are None/0

    Examples:
        >>> feet_inches_to_mm(5, 0)
        1524
        >>> feet_inches_to_mm(4, 6)
        1372
        >>> feet_inches_to_mm(0, 48)
        1219
    """
    feet = float(feet or 0)
    inches = float(inches or 0)
    
    if feet == 0 and inches == 0:
        return None
    
    total_inches = (feet * INCHES_PER_FOOT) + inches
    mm = total_inches * MM_PER_INCH
    
    if round_to_int:
        return int(round(mm))
    return round(mm, 2)


def format_length_inches(mm: Union[int, float, None], precision: int = 1) -> str:
    """
    Format a length in mm as a display string in inches.

    Args:
        mm: Length in millimeters
        precision: Decimal places for inches (default: 1)

    Returns:
        Formatted string like '48.0"' or '' if None/0

    Examples:
        >>> format_length_inches(1219)
        '48.0"'
        >>> format_length_inches(None)
        ''
    """
    if mm is None or mm == 0:
        return ''
    
    inches = mm_to_inches(mm, precision)
    if inches is None:
        return ''
    
    # Format without trailing zeros after decimal if whole number
    if inches == int(inches):
        return f'{int(inches)}"'
    return f'{inches:.{precision}f}"'


def format_length_feet_inches(mm: Union[int, float, None], show_zero_inches: bool = False) -> str:
    """
    Format a length in mm as a display string in feet and inches.

    Args:
        mm: Length in millimeters
        show_zero_inches: If True, show '0"' when inches is 0 (default: False)

    Returns:
        Formatted string like "5'-6\"" or "4'" or '' if None/0

    Examples:
        >>> format_length_feet_inches(1372)
        "4'-6\\""
        >>> format_length_feet_inches(1524)
        "5'"
        >>> format_length_feet_inches(1524, show_zero_inches=True)
        "5'-0\\""
    """
    if mm is None or mm == 0:
        return ''
    
    feet, inches = mm_to_feet_inches(mm)
    
    if feet == 0 and inches == 0:
        return ''
    
    if feet == 0:
        return f'{inches:.1f}"'
    
    if inches == 0 and not show_zero_inches:
        return f"{feet}'"
    
    # Round inches for display
    inches_display = round(inches, 1)
    if inches_display == int(inches_display):
        return f"{feet}'-{int(inches_display)}\""
    return f"{feet}'-{inches_display:.1f}\""


def parse_length_input(
    value: Union[str, int, float, None],
    input_unit: str = 'in'
) -> Optional[int]:
    """
    Parse a length input value and convert to mm (integer).

    This function handles various input formats and converts them to mm for storage.

    Args:
        value: The input value (can be string or number)
        input_unit: Unit of input - 'in' for inches, 'mm' for millimeters, 'ft' for feet

    Returns:
        Length in mm as integer, or None if invalid

    Examples:
        >>> parse_length_input(48, 'in')
        1219
        >>> parse_length_input('48', 'in')
        1219
        >>> parse_length_input(1000, 'mm')
        1000
        >>> parse_length_input(4, 'ft')
        1219
    """
    if value is None or value == '':
        return None
    
    try:
        numeric_value = float(value)
    except (ValueError, TypeError):
        return None
    
    if numeric_value <= 0:
        return None
    
    input_unit = input_unit.lower().strip()
    
    if input_unit == 'mm':
        return int(round(numeric_value))
    elif input_unit == 'in':
        return inches_to_mm(numeric_value, round_to_int=True)
    elif input_unit == 'ft':
        return feet_to_mm(numeric_value, round_to_int=True)
    else:
        # Default to inches for US market
        return inches_to_mm(numeric_value, round_to_int=True)


def add_inch_values_to_computed(computed: dict) -> dict:
    """
    Add inch-equivalent values to a computed results dictionary.

    This helper takes the computed output from the configurator engine
    and adds corresponding inch values for each mm field.

    Args:
        computed: Dictionary with mm values from configurator engine

    Returns:
        Dictionary with both mm and inch values added
    """
    if not computed:
        return computed
    
    # Map of mm fields to their inch equivalents
    mm_to_inch_fields = {
        'requested_overall_length_mm': 'requested_overall_length_in',
        'manufacturable_overall_length_mm': 'manufacturable_overall_length_in',
        'tape_cut_length_mm': 'tape_cut_length_in',
        'internal_length_mm': 'internal_length_in',
        'difference_mm': 'difference_in',
        'total_endcap_allowance_mm': 'total_endcap_allowance_in',
        'leader_allowance_mm_per_fixture': 'leader_allowance_in_per_fixture',
        'endcap_allowance_start_mm': 'endcap_allowance_start_in',
        'endcap_allowance_end_mm': 'endcap_allowance_end_in',
        'profile_stock_len_mm': 'profile_stock_len_in',
        'assembled_max_len_mm': 'assembled_max_len_in',
        'total_requested_length_mm': 'total_requested_length_in',
        'total_tape_length_mm': 'total_tape_length_in',
        'max_run_mm': 'max_run_in',
    }
    
    for mm_field, inch_field in mm_to_inch_fields.items():
        if mm_field in computed and computed[mm_field] is not None:
            computed[inch_field] = mm_to_inches(computed[mm_field], precision=2)
    
    # Process segments array if present
    if 'segments' in computed and isinstance(computed['segments'], list):
        for segment in computed['segments']:
            if 'profile_cut_len_mm' in segment:
                segment['profile_cut_len_in'] = mm_to_inches(segment['profile_cut_len_mm'])
            if 'lens_cut_len_mm' in segment:
                segment['lens_cut_len_in'] = mm_to_inches(segment['lens_cut_len_mm'])
            if 'tape_cut_len_mm' in segment:
                segment['tape_cut_len_in'] = mm_to_inches(segment['tape_cut_len_mm'])
            if 'start_leader_len_mm' in segment:
                segment['start_leader_len_in'] = mm_to_inches(segment['start_leader_len_mm'])
            if 'end_jumper_len_mm' in segment:
                segment['end_jumper_len_in'] = mm_to_inches(segment['end_jumper_len_mm'])
    
    # Process user_segments array if present (multi-segment fixtures)
    if 'user_segments' in computed and isinstance(computed['user_segments'], list):
        for segment in computed['user_segments']:
            if 'profile_cut_len_mm' in segment:
                segment['profile_cut_len_in'] = mm_to_inches(segment['profile_cut_len_mm'])
            if 'lens_cut_len_mm' in segment:
                segment['lens_cut_len_in'] = mm_to_inches(segment['lens_cut_len_mm'])
            if 'tape_cut_len_mm' in segment:
                segment['tape_cut_len_in'] = mm_to_inches(segment['tape_cut_len_mm'])
            if 'start_leader_len_mm' in segment:
                segment['start_leader_len_in'] = mm_to_inches(segment['start_leader_len_mm'])
            if 'end_jumper_len_mm' in segment:
                segment['end_jumper_len_in'] = mm_to_inches(segment['end_jumper_len_mm'])
    
    # Process runs array if present
    if 'runs' in computed and isinstance(computed['runs'], list):
        for run in computed['runs']:
            if 'run_len_mm' in run:
                run['run_len_in'] = mm_to_inches(run['run_len_mm'])
            if 'leader_len_mm' in run:
                run['leader_len_in'] = mm_to_inches(run['leader_len_mm'])
    
    return computed


def convert_build_description_to_inches(build_description: Optional[str]) -> str:
    """
    Convert a build description from mm to inches for public display.

    Takes a build description string that contains mm measurements and converts
    all mm values to inches. Used to create a user-friendly display version
    while keeping the original mm version for internal BOM use.

    Args:
        build_description: Build description string with mm values
            Example: "Seg 1: 8761mm | Start: END, 300mm leader | End: END, 300mm jumper"

    Returns:
        Build description with inches values
            Example: "Seg 1: 345.0\" | Start: END, 11.8\" leader | End: END, 11.8\" jumper"

    Examples:
        >>> convert_build_description_to_inches("Seg 1: 1000mm | Start: END, 300mm leader")
        'Seg 1: 39.4" | Start: END, 11.8" leader'
        >>> convert_build_description_to_inches("Seg 2: 2500mm | End: Solid Endcap")
        'Seg 2: 98.4" | End: Solid Endcap'
    """
    import re
    
    if not build_description:
        return ""
    
    def replace_mm(match):
        mm_value = float(match.group(1))
        inches_value = round(mm_value / MM_PER_INCH, 1)
        return f'{inches_value}"'
    
    # Replace patterns like "1234mm" with "48.6""
    # Match number followed by "mm" (with optional space before mm)
    result = re.sub(r'(\d+(?:\.\d+)?)\s*mm', replace_mm, build_description)
    
    return result


# Convenience constants for use in templates and JavaScript
CONVERSION_CONSTANTS = {
    'MM_PER_INCH': MM_PER_INCH,
    'MM_PER_FOOT': MM_PER_FOOT,
    'INCHES_PER_FOOT': INCHES_PER_FOOT,
}
