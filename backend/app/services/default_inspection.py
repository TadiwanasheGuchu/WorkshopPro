"""Default vehicle inspection checklist seeded for every organisation (CLAUDE.md §3.5).

Organisations can edit or replace it. Kept as plain data so the migration that seeds
existing organisations and the organisation bootstrap use the same content.
"""

DEFAULT_TEMPLATE_NAME = "Standard vehicle inspection"
DEFAULT_TEMPLATE_DESCRIPTION = "General intake and quality inspection covering all major systems."

# (section, label, guidance)
DEFAULT_ITEMS: tuple[tuple[str, str, str | None], ...] = (
    ("Exterior and bodywork", "Body panels", "Dents, scratches, rust, misaligned panels"),
    ("Exterior and bodywork", "Bumpers and trim", None),
    ("Exterior and bodywork", "Paint condition", None),
    ("Windows and mirrors", "Windscreen", "Chips, cracks in the driver's view"),
    ("Windows and mirrors", "Side and rear windows", None),
    ("Windows and mirrors", "Mirrors", None),
    ("Windows and mirrors", "Wiper blades", None),
    ("Tyres and wheels", "Front left tyre", "Tread depth, sidewall damage, pressure"),
    ("Tyres and wheels", "Front right tyre", "Tread depth, sidewall damage, pressure"),
    ("Tyres and wheels", "Rear left tyre", "Tread depth, sidewall damage, pressure"),
    ("Tyres and wheels", "Rear right tyre", "Tread depth, sidewall damage, pressure"),
    ("Tyres and wheels", "Spare wheel, jack and spanner", None),
    ("Tyres and wheels", "Rims", None),
    ("Brakes", "Front pads and discs", None),
    ("Brakes", "Rear pads, discs or shoes", None),
    ("Brakes", "Handbrake", None),
    ("Brakes", "Brake lines and hoses", "Leaks, chafing"),
    ("Steering and suspension", "Steering play", None),
    ("Steering and suspension", "Shock absorbers", None),
    ("Steering and suspension", "Bushes, ball joints and tie rods", None),
    ("Steering and suspension", "CV joints and boots", None),
    ("Engine and visible leaks", "Oil leaks", None),
    ("Engine and visible leaks", "Coolant leaks", None),
    ("Engine and visible leaks", "Drive belts", None),
    ("Engine and visible leaks", "Hoses", None),
    ("Engine and visible leaks", "Exhaust system", "Leaks, mountings, smoke"),
    ("Battery and electrical", "Battery and terminals", None),
    ("Battery and electrical", "Charging system", None),
    ("Battery and electrical", "Horn", None),
    ("Lights and indicators", "Headlights (low and high beam)", None),
    ("Lights and indicators", "Tail and brake lights", None),
    ("Lights and indicators", "Indicators and hazards", None),
    ("Lights and indicators", "Number plate and reverse lights", None),
    ("Interior and safety equipment", "Seat belts", None),
    ("Interior and safety equipment", "Seats and interior trim", None),
    ("Interior and safety equipment", "Warning triangle and fire extinguisher", None),
    ("Interior and safety equipment", "Air conditioning", None),
    ("Fluids", "Engine oil level and condition", None),
    ("Fluids", "Coolant level", None),
    ("Fluids", "Brake fluid", None),
    ("Fluids", "Power steering fluid", None),
    ("Fluids", "Washer fluid", None),
    ("Odometer and dashboard warnings", "Odometer reading recorded", None),
    ("Odometer and dashboard warnings", "Dashboard warning lights", "Record which lights are on"),
    ("Existing damage", "Pre-existing damage recorded", "Photograph damage present on arrival"),
)
