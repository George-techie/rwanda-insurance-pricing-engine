"""Build the ASSAR *information-engine* database: one SQL table per PDF table.

Unlike `build_db.py` (which uses 4 generic tables tuned for the deterministic
pricing calculators), this module emits ONE cleanly-named SQL table per table in
the ASSAR Version 3 manual. That layout is friendly to a text-to-SQL agent: a
natural-language question maps to a single, well-named table with descriptive
columns, so users can query the manual's numbers instead of reading the PDF.

    python -m assar.build_info_tables            # build data/assar_info.db
    python -m assar.build_info_tables --schema   # print the table/column catalog

Numeric rate values are reused from `assar/seed.py` (already verified cell-by-cell
against the source PDF). Text labels are EXACT verbatim strings from the PDF so
an agent's string/LIKE matching lines up with the source wording. The large-risk
registers (pages 76-80) are transcribed here because they were not part of the
pricing seed.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from . import seed

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "assar_info.db"


def _unit_for(table: str, col: str, ctype: str) -> tuple[str, str]:
    """Infer (unit, description) for a column, mostly from its name suffix."""
    if table == "market_parameters" and col == "value":
        return "varies (see the 'unit' column)", "Parameter value; unit given per row"
    if col.endswith("_per_mille"):
        return "per mille (‰)", "Rate per 1,000 of sum insured (NOT percent)"
    if col.endswith("_rwf"):
        return "Rwandan Francs (RWF)", "Monetary amount in RWF"
    if col.endswith("_pct") or col.startswith("pct_") or "_pct_" in col:
        return "percent (%)", "Rate/percentage applied to sum insured or limit"
    if col == "fraction_of_annual_premium":
        return "fraction", "Multiplier of the annual premium (e.g. 0.5 = 50%)"
    if col.endswith("_days"):
        return "days", "Number of days"
    if col.endswith("_weeks"):
        return "weeks", "Number of weeks"
    if col.endswith("_months"):
        return "months", "Number of months"
    if col == "value" and ctype.upper() in ("REAL", "INTEGER"):
        return "number", "Numeric value"
    return "—", "Text label / description"


def _zip(labels, seed_rows):
    """Pair exact PDF labels with verified seed rows; fail loudly on drift."""
    labels = list(labels)
    seed_rows = list(seed_rows)
    assert len(labels) == len(seed_rows), (
        f"label/seed length mismatch: {len(labels)} labels vs {len(seed_rows)} rows")
    return labels, seed_rows


# ---------------------------------------------------------------------------
# EXACT verbatim labels transcribed from the PDF, in the SAME order as the
# corresponding seed lists (so we reuse the verified numbers, exact wording).
# ---------------------------------------------------------------------------

SPECIAL_PERILS_LABELS = [
    "Earthquake", "Storm, Tempest, Flood & Tornado", "Riot & Strike",
    "Malicious damage", "Burst Pipe (water damage)",
    "Impact (vehicle, aircraft, animal…)", "Bush Fire", "Subsidence",
    "Spontaneous Combustion",
]

FIRE_LABELS = [
    "Aerated Water Factories, Mineral Water & Water Treatment Plant",
    "Agricultural Show Grounds", "Airports, Airfields & Hangers",
    "Aluminum Pressing Works", "Auction Sale Rooms", "Automobile Show Rooms",
    "Bacon Factories", "Bakeries & Biscuits Manufacture", "Banks",
    "Bars and Gaming Rooms", "Blacksmiths", "Boarding Houses", "Boat Houses",
    "Boot & Shoe Factories", "Brick & Tile Works",
    "Broadcasting Stations & Telecommunication Houses",
    "Buildings in course of construction",
    "Butter and Cheese factories, Creameries and Diaries",
    "Cafes & Restaurants", "Candle Manufacturing", "Car bonds/ Warehouses",
    "Ceramic & Pottery Works", "Chemical Insecticides and Sprays",
    "Chemical manufacturing & Storage", "Churches, Chapels, Mosques & Temples",
    "Cigarette Factories", "Cinemas and Theatres", "Clothing Factories",
    "Clubs (Discotheques)", "Coal and/ or Compost and Manure in the Open",
    "Coffee Mills or Factories", "Cold Storage & Ice Factories", "Collieries",
    "Concrete Block Works (Wet Process), Cement Plant",
    "Confectioneries (Manufacturing)", "Cosmetic Factories", "Cotton Factories",
    "Distilleries (Chemical)", "Dry Cleaners",
    "Dwellings & Domestic Outbuildings (i.e Apartment)",
    "Electric Light & Power Stations", "Engineering Workshops",
    "Fish & Meat Processing", "Flax Factories", "Flour & Mealie Mills",
    "Fruit Juice Factories", "Garages", "Ghee Refineries", "Glass Factories",
    "Gold Smiths", "Goods in Government Bonded Warehouses & Other Warehouses",
    "Goods in the Open, Not otherwise Provided For",
    "Grass/ papyrus/ makuti / banana fibre thatched buildings",
    "Hospitals", "Hotels", "Jaggery Industries", "Jam & Canning Factories",
    "Knitting Works", "Joinery", "Laundries",
    "Masonic and/ or Other Fraternal Meeting Halls", "Match Manufacturing",
    "Mining Risks", "Nail, Screw, Needle, Pin, Barbed Wire & Wire Mesh Makers",
    "Offices", "Depots for Oil Storage, petrol, gas, essence and like",
    "Factories for Oil, petrol, gas, essence & Fat and like",
    "Power Houses, Power Plant (i.e:Hydro Power Plant, Peat Power Plat and like)",
    "Paint & Vanish Factories", "Paper Industries",
    "Petrol & Gas Filling Stations",
    "Pharmaceutical : Tablet, Pill, Capsule Making and Bottle Filling",
    "Plastic Industries", "Poultry Houses", "Printing Works/ Carton Factories",
    "Pyrethrum Drying Sheds", "Quarries", "Razor Blade Makers", "Rice Mills",
    "Rubber Goods Factories, Tyre Factories & Tyre Re-treading Works",
    "Schools (Day)", "Schools & Colleges (Boarding) & Hostels",
    "Shops, Super Markets, Markets & Malls", "Silent/ Dormant Risks",
    "Sisal Factories", "Soap Factories", "Spray Painting", "Stables",
    "Steel Tubes, Steel Bed & Steel Furniture Makers",
    "Steel Rolling Mills, Steel Bar, Strip & Girder Makers",
    "Sugar Mills & Refinery", "Tanneries", "Tea Factories & Withering Houses",
    "Timber Stores & Sheds Strong", "Tobacco Factories", "Unoccupied Buildings",
    "Vinegar Factories", "Wattle Extract Factories",
    "Wattle (Dry) Back Factories", "Wine Bottling Premises",
    "Woodworkers, Carpenters, Saw Mills, Joiners, Cabinet Makers & Upholsterers",
    "Thatched roof buildings", "Other Occupancy/Risks not specified",
]

PUBLIC_LIABILITY_LABELS = [
    "Utilities", "Manufacturing", "Hotel/Restaurant/Tourism",
    "Telecommunication/Financial Services", "Chemical industries", "Others",
]

EMPLOYERS_LIABILITY_LABELS = [
    "Businessmen and the like", "Engineers and the like",
    "Office and administration",
    "Manufacturing class 1 (person not involved in hazardous activities e.g office &administration )",
    "Manufacturing class 1 (person involved in hazardous activities e.g person operating on industrial processing machines )",
    "Construction Workers",
    "Drivers; Security Guards, Turn Boys, and Mining workers",
]

PRODUCT_LIABILITY_LABELS = [
    "Manufacturing of human food",
    "Manufacturing of electronics and construction materials",
    "Chemical industries", "Others",
]

PROFESSIONAL_INDEMNITY_LABELS = [
    "Medical malpractice (Doctors, Hospitals, clinics,….)",
    "Engineers, Architects, Builders",
    "Lawyers, Accountants, Auditors, Surveyors, Property valuers",
    "Insurance Agents", "Others (e.g Pharmacy,…)",
]

PA_GPA_LABELS = EMPLOYERS_LIABILITY_LABELS + ["Student at internship"]

EAR_CAR_LABELS = [
    "Residential buildings", "Commercial & Administrative buildings",
    "Water tanks", "Water pipelines",
    "Power transmission lines & Public Lighting", "Excavation Works", "Stadium",
    "Bridges", "Dams", "Petroleum Tank Farms", "Roads in Urban Areas",
    "Roads in Rural Areas", "Roads-Open Area Paving", "Airports", "Ports",
    "Power Plants/Electricity Generating company-Genset Power Plant",
    "Power Plants/Electricity Generating company-Hydroelectric Power Plant",
    "Power Plants/Electricity Generating company-Gas turbines",
    "Power Plants/Electricity Generating company-Geothermal Plant",
    "Power Plants/Electricity Generating company-Coal Power Plant",
    "Power Plants/Electricity Generating company-Flywheel Energy Storage",
    "Power Plants/Electricity Generating company-Hybrid power plant",
    "Power Plants/Electricity Generating company-Combined cycle gas turbine plant",
    "Power Plants/Electricity Generating company-Wind farm",
    "Power Plants/Electricity Generating company-Solar power plant",
    "Communication towers",
]

MACHINERY_LABELS = [
    "Agriculture Industry - Combine Harvester",
    "Agriculture Industry - Crawler Type/ Vehicle with caterpillar truck",
    "Agriculture Industry - Fodder Drying/ Straw baling",
    "Leather Industry", "Paper/ Cardboard industry",
    "Storage Facility (Cold Storage, Chillers, Deep Freezer)",
    "Wood Working Industry", "Residence, Office, Hospital Machinery",
    "Cinema/ Film Projectors", "Food & Fodder Industry",
    "Metal Producing Industry", "Electrical Heated, Smelting, Furnace & Others",
    "Scrap Shearer (Hammer, Shredder, Crasher Plant/ Steel Furnace)",
    "Metal Working Industry - Riveting & Welding Machine",
    "Metal Working Industry - Cutting & Facing Machine Tools",
    "Metal Working Industry - Forging Equipment (Hot Work)",
    "Metal Working Industry - Forging Equipment (Cold Work)",
    "Metal Working Industry - Rolling Mill (Hot &Cold)",
    "Metal Working Industry - Heat Treatment/ Wire Drawing/ Equipment/ Sheet & Metal Working Equipment",
    "Chemical Industry - Injection/ Blow Molding Extruders, Platter Presses, Vulcanizing Presses, Mixture Rolling Mills, Pelletizing Machines, Cocking Plant",
    "Chemical Industry - Other Machines & Equipment", "Graphic Industry",
    "Mining Industry - Surface", "Transport & Traffic System",
    "Conveyors, Cranes, Winches, Hoist, Filling Equipment, etc (For CPM)",
    "Transformers", "Others",
]

BONDS_LABELS = [
    "Performance Bond", "Advance Payment Bond", "Financial Guarantee",
    "Bid Bond", "Customs Bond (RCTG Transit & Clearing)", "Bonded warehouse",
    "Temporary Importation",
]

FIDELITY_LABELS = [
    "Financial Services (Banks, Forex Bureau, Microfinance Institutions, Sacco)",
    "Distribution Channels & Sales/ Purchasing Staff",
    "Other Risks such as offices not exposed to huge Sums of Money",
    "Security Firms",
]

MONEY_LABELS = [
    "Money in Transit (single trip)", "In Safe/Strongroom", "In ATM Machine",
    "Out of Safe", "In Personal Custody of Senior Employee",
    "The Safe and ATM Machine itself",
]

MONEY_CARRYINGS_BANDS = [
    "0 < 10 BN", "10 < 15 BN", "15 < 20 BN", "20 < 30 BN", "30 < 50 BN",
    "Above 50 BN",
]

# Transit commodity classifications (verbatim) keyed by PDF code.
COMMODITY = {
    "1.a": "Raw Agricultural Produce such as Cotton; Tea; Cocoa; Rice in Bags/Bales/Chests",
    "1.b": "Grains in Bags such as Maize; Beans; Peas. Exclude damage caused by Rain Water other than from the sea, Inherent Vice",
    "2.a": "Non Fragile General Merchandise/ Manufactured goods such as Machinery; Iron Products not susceptible to pilferage. Exclude Rust, Oxidation and discoloration",
    "2.b": "Non Fragile General Merchandise/ Manufactured goods such as Machinery; Iron Products such as Spare Parts; Batteries; Tyres; Cigarettes; Paper all susceptible to Pilferage; Water damage",
    "3": "Semi-Fragile merchandize / Manufactured goods such as Electrical Appliances",
    "4": "Fragile General Merchandize goods such as Glass; Glassware; Glass Louvers; Glass Sheets; Chinaware's; Wines, Liquor but excluding Ornamented Glass",
    "5.a": "Chemical Products in Drums. Exclude Explosives and inherent vice",
    "5.b": "Chemicals / Cement / Fertilizer in Bags excluding spillage, rain water damage, inherent vice other than by Sea Water",
    "5.c": "Pharmaceuticals",
    "6.a": "Food and Foodstuffs and Confectionery in Cans",
    "6.b": "Food and Foodstuffs ( sugar, salt and the like) and Confectionery in Bags / Cartons",
    "7.a": "Bulk Cargo Petroleum Products",
    "7.b": "Bulk Cargo (Grains and Others) and Edible Oils",
    "7.c": "Other Liquid and beers",
    "8": "Matches, Fireworks, Explosives, Gunpowder, Flammables, Acids",
    "9": "Copper and other precious metals",
    "10.a": "Household Goods and Personal Effects: a. Professionally packed",
    "10.b": "Household Goods and Personal Effects: b. Not professionally packed",
}


# ---------------------------------------------------------------------------
# Tables transcribed directly from the PDF (not present in the pricing seed)
# ---------------------------------------------------------------------------

# Large risks register — PROPERTY (pages 76-79). (property, insured_value_rwf)
LARGE_RISKS_PROPERTY = [
    ("Rwanda Management Institute (RMI)", 3010646514),
    ("Zigama Credit and Savings Society", 9557482180),
    ("Zigama Credit and Savings Society", 96386683548),
    ("East African Granite Industries Ltd", 6527891604),
    ("Ministry of Defence", 65890026645),
    ("Ruliba Clays Ltd", 7049381896),
    ("Gorilla Investment Company Ltd", 7500000000),
    ("Beijing Decoration Design & Engineering Co. Ltd", 2375340000),
    ("Akagera Game Lodge", 4113799718),
    ("Institute of National Museums of Rwanda", 4127135583),
    ("Rwanda Standards Board", 3028902407),
    ("Etablissement Kivu Motor Garage Pascal", 2344493223),
    ("District Karongi", 2036944078),
    ("National Institute of Statistics of Rwanda", 9727927271),
    ("District Karongi", 2036944078),
    ("Agahozo Shalom Youth Village", 7033765853),
    ("National Identification Agency", 3483034050),
    ("National Identification Agency", 3483034050),
    ("Intare Investments Ltd", 34629356500),
    ("Hopital Kibagabaga", 3178445940),
    ("Societe Premidis Sarl C/O Shiva Prasad Reddy", 2737922963),
    ("District de Gisagara", 3053455508),
    ("Minisante", 7466237317),
    ("Rwanda Correctional Service", 9608941740),
    ("District de Nyamasheke", 2429748114),
    ("Hotel Villa Portofino Kigali Ltd", 12361907600),
    ("Hashi Energy Rwanda Ltd", 12463267738),
    ("University of Rwanda", 39620803980),
    ("District Kirehe", 2402601990),
    ("Oshen Health Care Rwanda Ltd", 5548544980),
    ("Hotel Villa Portofino Kigali Ltd", 12361907600),
    ("Embassy of the Republic of Uganda", 2260340375),
    ("Cimerwa Ltd", 15000000000),
    ("Cimerwa Ltd", 7082436321),
    ("University of Rwanda", 33320803980),
    ("Ministry of Trade and Industry (MINICOM)", 7502823903),
    ("EDCL", 7000000000),
    ("TECOS", 2126000000),
    ("Kigali Heights Development Company", 38347930429),
    ("Kigali Heights Development Company", 32323660429),
    ("Hopital Butaro", 2316350655),
    ("Mayfair Insurance Company Rwanda", 12226310352),
    ("Mayfair Insurance Company Rwanda", 11489799213),
    ("University of Rwanda", 33320803980),
    ("Epic Hotel & Suites Ltd", 12069607360),
    ("Epic Hotel & Suites Ltd", 19129031888),
    ("Bralirwa SA", 52258500000),
    ("Rwanda Trading Company Ltd", 5528771523),
    ("ERP Rwanda", 5415200000),
    ("MINAFFET", 5050936000),
    ("Rwanda Trading Company Ltd", 5028771523),
    ("Shagasha Tea Co. Ltd", 4709641422),
    ("Mulindi Factory Co. Ltd", 4645000000),
    ("Fatima Hotel", 4470187835),
    ("Rwanda Standards Board (RSB)", 4395460000),
    ("Mount Kenya University", 4000000000),
    ("Imizi Eco-Tourism Development Ltd", 3553878570),
    ("Societe Kigali Estate SA.", 3442690850),
    ("Fatima Hotel", 2969125223),
    ("Mukamasabo Josephine", 2541941000),
    ("Discentre Ltd", 2400000000),
    ("Rwanda Trading Company Ltd", 2036059871),
    ("Nitora Rwanda Limited", 2000000000),
    ("Africa Improved Foods", 39003400000),
    ("SP Rwanda", 28000000000),
    ("Perfect City Developments (R) Ltd", 21575000000),
    ("MIC MIC", 19111520450),
    ("National Electoral Commission", 13608375000),
    ("Office of the Auditor General", 13608375000),
    ("Rwanda Revenue Authority", 13608375000),
    ("Hotel Villa Portofino Kigali", 12483066000),
    ("Ministry of Lands and Forestry (MINILAF)", 12254882795),
    ("Dubai World Rwanda", 9975360000),
    ("Inyange Industries", 9109543859),
    ("Cogebanque", 8873385478),
    ("Africa Improved Foods", 8479000000),
    ("Inyange Industries", 7011334337),
    ("Trust Industries Ltd", 6000000000),
    ("Dove Hotel Ltd", 5583915720),
    ("Masaka Hospital", 5570468647),
    ("Horizon Construction Ltd", 5058783779),
    ("Real Contractors", 3496679649),
    ("Real Contractors", 4253256927),
    ("United Enrichment Partners Ltd", 4656364770),
    ("Energicotel Ltd", 5633305414),
    ("Development Bank of Rwanda (BRD)", 6887408764),
    ("Hygebat", 7910206960),
    ("Horizon Construction", 16440000000),
    ("Horizon Construction", 16440000000),
    ("Inyange Industries Ltd", 28308231718),
    ("Energy Utility Corporation (EUCL) Limited", 150954516393),
    ("Energy Utility Corporation (EUCL) Limited", 149427180658),
    ("Skol Brewery Ltd", 51133248950),
    ("Champion Investment Corporation (CHIC) Ltd", 18000000000),
    ("Inkundamahoro Ltd", 13000000000),
    ("Neuro-Psychiatric Hospital", 5663925990),
    ("Soras Assurances Generales", 5857669174),
    ("Soras Assurances Generales", 6821953445),
    ("Printex Ltd", 7594773597),
    ("Soras Vie Ltd", 9169812992),
    ("Sorwathe Ltd", 10492838644),
    ("Hotel des Mille Collines", 14069299510),
    ("WASAC", 15083521472),
    ("Cimerwa Ltd", 283437311593),
    ("Airtel-Tigo", 174160058870),
    ("Ultimate Concept Ltd", 153506269020),
    ("Master Steel Limited", 39461068761),
    ("Runh Power Corp., Ltd", 25490095930),
    ("Soenergy Rwanda Ltd", 17200000000),
    ("Kigali Business Center Ltd", 15970575000),
    ("Gasabo Grain Milling Company Ltd", 8729480980),
    ("Rwaza Hydropower Ltd", 8700000000),
    ("Thana Twagirayezu", 8673690148),
    ("Tree Top Complex Ltd", 5268000000),
    ("Tropical Plaza", 5000000000),
    ("Lemigo Hotel", 5000000000),
    ("Horizon Sopyrwa", 4583861664),
    ("CO-CPPAR", 4400000000),
    ("Caritas Rwanda", 4017332250),
    ("Energy Resources Petroleum Ltd", 4000000000),
    ("ISCO Security Company", 4000000000),
    ("Development Bank of Rwanda Plc", 3788389524),
    ("Roba General Merchants Ltd", 3600000000),
    ("Caritas Rwanda", 3405732750),
    ("Century Park Hotel & Residence", 3240544825),
    ("KIM University", 3068728503),
    ("Kinazi Cassava", 2846832000),
    ("Kakivu Mousse S.A.R.L", 2447370000),
    ("AOS Ltd", 2422268307),
    ("Ignite Power Ltd", 2400000000),
    ("Ignite Power Ltd", 2400000000),
    ("Belecom Ltd", 2391219150),
    ("Edouard Mukeka", 2366610000),
    ("Rwanda Girls Initiative", 2345206833),
    ("Grazia Apartments Ltd", 2300000000),
    ("Tele 10 Ltd", 2113919800),
    ("Landy Industries (R) Ltd", 2100000000),
    ("Sulfo Rwanda Industries Ltd", 2087994000),
    ("Spelman Estates (Rwanda) Ltd", 2000000000),
    ("Rusirare Jacques Ameki Color Ltd", 5405493472),
    ("Acacia Hotel", 13120000000),
    ("Access Bank Ltd", 8979012823),
    ("African Hotel Development Rwanda", 7467597456),
    ("Afriprecast", 7569733185),
    ("Akagera Business Group Ltd", 7295300300),
    ("Angelique International Ltd", 11965032872),
    ("Banque Populaire du Rwanda", 240280000000),
    ("China Civil Engineering Construction Corporation (CCECC)", 5273792470),
    ("China Civil Engineering Construction", 72068426824),
    ("Club House La Palisse (Golden Tulip Hotel)", 13000000000),
    ("Energy Utility Corporation Limited /EUCL", 90100000000),
    ("Fair Construction Sarl", 8552743840),
    ("I&M Bank (Rwanda) Ltd", 9534271084),
    ("Magerwa Limited", 10502419101),
    ("Mota-Engil, Engenharia e Construcao", 80000000000),
    ("Mount Meru Soyco Ltd", 14994000000),
    ("PBG Rwanda Ltd", 8990924400),
    ("Primecement", 10179000000),
    ("Rwanda Airports Company (RAC)", 41717774505),
    ("Rwanda Biomedical Center (RBC)", 26991502146),
    ("Rwanda Social Security Board (RSSB)", 77425831316),
    ("Top International Engineering Corporation (TIEC)", 9579844167),
]

# Large risks register — ENGINEERING (page 80).
LARGE_RISKS_ENGINEERING = [
    ("National Identification Agency", 3379000000),
    ("Oshen Health Care Rwanda Ltd", 5468494379),
    ("Cimerwa Ltd", 4000000000),
    ("NPD Ltd", 8806022733),
    ("Ministry of Trade and Industry (MINICOM)", 7489323803),
    ("Horizon Construction Ltd", 5058783779),
    ("Africa Improved Foods", 8479000000),
    ("Inyange Industries", 7011334337),
    ("Energy Utility Corporation (EUCL) Limited", 137022522795),
    ("Stecol Corporation", 45557036029),
    ("Skol Brewery Ltd", 43486233269),
    ("China Road and Bridge Corporation", 47791638525),
    ("China Road and Bridge Corporation", 29788197622),
    ("Century Park Hotel & Residence", 13839044683),
    ("Technofab Engineering Ltd", 11027857781),
    ("Afrilandscapes Ltd", 3118249300),
    ("Unipharma", 735300000),
    ("Sorwathe Ltd", None),
    ("Hotel des Mille Collines", 14069299510),
    ("WASAC", 15083521472),
    ("Cimerwa Ltd", 283437311593),
    ("Airtel-Tigo", 174160058870),
]

# Large risks register — ACCIDENT CLASSES (page 80).
LARGE_RISKS_ACCIDENT = [
    ("Kipharma", 1056420000),
    ("UAP Insurance Rwanda Ltd", 789010704),
    ("Agrotech", 739080000),
]

# Market-wide parameters (scattered through pages 12-16, 75). These mix units
# (RWF vs %), so each row carries its own `unit`.
MARKET_PARAMETERS = [
    ("minimum_policy_fee", 5000, "RWF", "Minimum policy/administrative fee, net of taxes (p12)"),
    ("fea_discount", 15.0, "percent (%)", "Fire Extinguishing Appliances discount off gross premium (p16)"),
    ("commission_lead", 25.0, "percent (%)", "Approved commission rate for lead insurer under co-insurance (p75)"),
    ("stock_declaration_discount", 10.0, "percent (%)", "Discount on stock declaration policies (p29)"),
    ("voluntary_deductible_saving_cap", 33.33, "percent (%)", "Max premium saving as % of the excess amount (p13)"),
    ("max_refund_of_deposit_premium", 25.0, "percent (%)", "Max refund of deposit premium on declaration policies (p29)"),
]

# Minimum premiums by class (RWF, net of taxes & fees) — pages 33-72.
MINIMUM_PREMIUMS = [
    ("Money", 200000, "Entire money insurance policy; cover <= 12 months"),
    ("Public Liability", 100000, "Cover <= 12 months"),
    ("Employers' Liability", 100000, "Cover <= 12 months"),
    ("Product Liability", 100000, "Cover <= 12 months"),
    ("Professional Indemnity", 200000, "Other professions"),
    ("Professional Indemnity (Insurance Agents)", 25000, "Insurance agents"),
    ("Personal Accident", 25000, "Others"),
    ("Personal Accident (student at internship)", 15000, "Students at internship <= 3 months"),
    ("Group Personal Accident", 50000, "Others"),
    ("Group Personal Accident (student at internship)", 30000, "Students at internship <= 3 months"),
    ("Bid Bond", 10000, "Net premium"),
    ("Other Bonds", 30000, "Net premium"),
    ("Fidelity Guarantee", 200000, "Cover <= 12 months"),
]

# Consequential Loss - Dual Basis Wages Cover matrix (page 26). For each
# indemnity period (months) and initial period of 100% cover (weeks), the table
# gives, per percentage of wages insured for the remainder, two figures:
# A = percentage of the basis rate, B = number of weeks of alternative
# insurance. The manual notes these multipliers are "not commonly used".
# Each row's list is 18 values: A,B for each wage percentage below, in order.
# Values are transcribed verbatim from p.26 (two appear to be source typos:
# 18-month rows show 11 in the 75% A column, and 30-month/39-week shows 195 in
# the 66.75% A column).
DUAL_BASIS_WAGE_PCTS = [10, 15, 20, 25, 33.33, 40, 50, 66.75, 75]
DUAL_BASIS_WAGES = [
    (12, 4, [55, 7, 59, 9, 64, 10, 66, 10, 76, 13, 83, 16, 94, 19, 113, 20, 122, 33]),
    (12, 5, [60, 9, 64, 10, 67, 10, 72, 12, 80, 15, 87, 16, 98, 22, 115, 29, 124, 36]),
    (12, 6, [63, 10, 66, 10, 70, 12, 75, 13, 83, 16, 90, 17, 100, 22, 117, 29, 125, 36]),
    (12, 8, [69, 10, 71, 12, 76, 13, 81, 15, 88, 17, 95, 19, 104, 24, 119, 33, 127, 36]),
    (12, 13, [83, 16, 86, 16, 90, 17, 94, 19, 100, 22, 105, 24, 113, 29, 125, 36, 131, 39]),
    (12, 26, [114, 29, 116, 29, 118, 33, 120, 33, 123, 36, 126, 36, 130, 39, 137, 42, 140, 46]),
    (18, 4, [41, 9, 46, 12, 49, 13, 54, 15, 64, 19, 71, 24, 83, 36, 102, 54, 11, 58]),
    (18, 5, [45, 12, 49, 13, 52, 15, 58, 16, 67, 22, 74, 26, 85, 39, 103, 54, 11, 61]),
    (18, 6, [46, 12, 50, 16, 55, 16, 60, 17, 69, 24, 76, 29, 87, 39, 104, 54, 11, 61]),
    (18, 8, [49, 13, 54, 15, 59, 17, 64, 19, 72, 26, 79, 33, 89, 42, 106, 56, 11, 62]),
    (18, 13, [59, 17, 64, 19, 68, 22, 73, 26, 80, 33, 86, 39, 95, 49, 110, 58, 118, 63]),
    (18, 26, [80, 33, 83, 36, 87, 39, 90, 42, 96, 49, 100, 52, 107, 56, 118, 63, 123, 67]),
    (24, 4, [55, 7, 59, 9, 64, 10, 66, 10, 76, 13, 83, 16, 94, 19, 113, 20, 122, 72]),
    (24, 5, [36, 12, 38, 13, 43, 16, 48, 19, 57, 29, 64, 39, 74, 52, 91, 65, 100, 77]),
    (24, 6, [37, 13, 40, 15, 45, 17, 50, 22, 58, 29, 65, 39, 75, 52, 92, 67, 100, 77]),
    (30, 8, [38, 13, 43, 16, 48, 19, 53, 24, 61, 33, 67, 42, 77, 54, 93, 67, 101, 79]),
    (30, 13, [46, 17, 51, 22, 55, 26, 59, 33, 67, 42, 72, 49, 81, 56, 96, 69, 103, 79]),
    (30, 26, [62, 36, 66, 39, 69, 46, 73, 49, 78, 54, 83, 58, 90, 65, 102, 76, 108, 81]),
    (30, 39, [71, 46, 74, 52, 77, 54, 80, 56, 85, 60, 89, 65, 95, 69, 195, 78, 110, 82]),
    (30, 52, [80, 56, 83, 58, 85, 60, 88, 63, 92, 67, 95, 69, 100, 74, 108, 81, 113, 87]),
    (36, 4, [23, 12, 28, 16, 33, 22, 38, 29, 47, 46, 54, 56, 64, 69, 81, 100, 89, 112]),
    (36, 5, [25, 13, 30, 17, 35, 24, 40, 33, 48, 49, 59, 58, 65, 71, 82, 100, 90, 115]),
    (36, 6, [27, 15, 31, 19, 36, 26, 41, 36, 49, 49, 56, 60, 66, 74, 82, 100, 90, 115]),
    (36, 8, [29, 16, 34, 22, 38, 29, 43, 39, 51, 54, 58, 63, 67, 74, 83, 104, 91, 117]),
    (36, 13, [34, 22, 38, 29, 43, 39, 48, 49, 55, 58, 61, 67, 70, 78, 85, 107, 93, 120]),
    (36, 26, [45, 42, 48, 49, 52, 54, 56, 60, 63, 69, 68, 76, 76, 89, 89, 112, 95, 122]),
    (36, 39, [51, 54, 54, 56, 58, 63, 61, 67, 67, 74, 72, 81, 79, 92, 91, 117, 97, 125]),
    (36, 52, [57, 60, 60, 65, 63, 69, 66, 74, 72, 81, 76, 89, 83, 104, 93, 120, 99, 128]),
]


def build(db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    for (name,) in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        cur.execute(f"DROP TABLE IF EXISTS {name}")

    # 1. Voluntary deductible discount schedule (p13)
    conn.execute("""CREATE TABLE voluntary_deductible_discount(
        deductible_band TEXT, discount_pct REAL)""")
    conn.executemany("INSERT INTO voluntary_deductible_discount VALUES(?,?)", [
        ("Up to 250,000", 5.0), ("250,000 up to 500,000", 7.5),
        ("500,000 up to 1,000,000", 10.0), ("1,000,000 up to 2,000,000", 12.5),
        ("2,000,000 up to 3,000,000", 15.0), ("3,000,000 up to 4,000,000", 17.5),
        ("4,000,000 up to 5,000,000", 20.0),
    ])

    # 2. Special perils (p15)
    conn.execute("""CREATE TABLE special_perils(
        special_peril TEXT, commercial_industrial_rate_pct REAL,
        residential_rate_pct REAL, note TEXT)""")
    labels, rows = _zip(SPECIAL_PERILS_LABELS, seed.SPECIAL_PERILS)
    conn.executemany("INSERT INTO special_perils VALUES(?,?,?,?)",
                     [(lbl, c, r, None) for lbl, (_, c, r) in zip(labels, rows)])
    conn.execute("INSERT INTO special_perils VALUES(?,?,?,?)",
                 ("Full Explosion", None, None, "Already covered under standard fire policy"))

    # 3. Short-period scale (p16)
    conn.execute("""CREATE TABLE short_period_scale(
        cover_period TEXT, fraction_of_annual_premium REAL)""")
    conn.executemany("INSERT INTO short_period_scale VALUES(?,?)", [
        ("1 Day Cover", 1/24), ("3 Days Cover", 1/12), ("1 Week Cover", 1/8),
        ("1 Month Cover", 1/4), ("2 Months Cover", 3/8), ("3 Months Cover", 1/2),
        ("4 Months Cover", 5/8), ("6 Months Cover", 3/4), ("8 Months Cover", 7/8),
        ("Over 8 Months Cover", 1.0),
    ])

    # 4. Fire & allied perils — commercial/administrative (p19-22)
    conn.execute("""CREATE TABLE fire_allied_perils(
        risk_category TEXT, standard_fire_rate_pct REAL,
        fire_all_special_perils_rate_pct REAL, note TEXT)""")
    fire_vals = [(s, a) for c, s, a in seed.FIRE if not c.startswith("private_dwelling")]
    labels, rows = _zip(FIRE_LABELS, fire_vals)
    conn.executemany("INSERT INTO fire_allied_perils VALUES(?,?,?,?)",
                     [(lbl, s, a, None) for lbl, (s, a) in zip(labels, rows)])
    conn.execute("INSERT INTO fire_allied_perils VALUES(?,?,?,?)",
                 ("Green houses", None, None, "Refer to reinsurers' rate"))

    # 5. Fire private dwellings (p22)
    conn.execute("""CREATE TABLE fire_private_dwellings(
        description TEXT, all_perils_rate_pct REAL, fire_only_rate_pct REAL)""")
    conn.executemany("INSERT INTO fire_private_dwellings VALUES(?,?,?)", [
        ("Buildings inclusive of Boundary Walls and Out buildings", 0.15, seed.FIRE_ONLY_DWELLING),
        ("Contents", 0.15, seed.FIRE_ONLY_DWELLING),
    ])

    # 6. Consequential loss — basis-rate items (p24)
    conn.execute("""CREATE TABLE consequential_loss_basis(
        item TEXT, pct_of_fire_material_damage_rate REAL)""")
    conn.executemany("INSERT INTO consequential_loss_basis VALUES(?,?)", [
        ("On Gross Profit", 150.0), ("On Auditors Fees", 125.0), ("On Wages", 100.0),
    ])

    # 7. Consequential loss — indemnity-period multiplier (p24)
    conn.execute("""CREATE TABLE consequential_loss_indemnity_period(
        indemnity_period TEXT, pct_of_basis_rate REAL)""")
    ci_label = lambda m: "Exceeding 72 months" if m == 999 else f"Not exceeding {m} months"
    conn.executemany("INSERT INTO consequential_loss_indemnity_period VALUES(?,?)",
                     [(ci_label(m), v) for m, v in seed.CI_INDEMNITY])

    # 8. Business interruption — voluntary time excess discount (p24/57)
    conn.execute("""CREATE TABLE business_interruption_time_excess(
        time_excess_days INTEGER, applicable_discount_pct REAL)""")
    conn.executemany("INSERT INTO business_interruption_time_excess VALUES(?,?)",
                     seed.CI_VOLUNTARY_TIME_EXCESS)

    # 9. Burglary — full value basis rates (p28)
    conn.execute("CREATE TABLE burglary_full_value(goods_type TEXT, minimum_rate_pct REAL)")
    conn.executemany("INSERT INTO burglary_full_value VALUES(?,?)", [
        ("Ordinary Goods", 0.3), ("High Valued Goods (such as precious metals)", 0.5),
    ])

    # 10. Burglary / stock — first-loss multipliers (p28-29)
    conn.execute("CREATE TABLE first_loss_multiplier(ratio_of_full_value_at_risk TEXT, multiplier_pct REAL)")
    conn.executemany("INSERT INTO first_loss_multiplier VALUES(?,?)", [
        ("Ratio of 25% or less of Full Value @ Risk", 50),
        ("Ratio of 26% to 30% of Full Value @ Risk", 60),
        ("Ratio of 31% to 35% of Full Value @ Risk", 70),
        ("Ratio of 36% to 45% of Full Value @ Risk", 80),
        ("Ratio of 46% to 50% of Full Value @ Risk", 90),
        ("Ratio above 50% of Full Value @ Risk", 100),
    ])

    # 11. Bankers Blanket Bond (p31)
    conn.execute("CREATE TABLE bankers_blanket_bond(description_of_risk TEXT, rate_pct REAL, note TEXT)")
    conn.execute("INSERT INTO bankers_blanket_bond VALUES(?,?,?)",
                 ("Financial Services (Banks, Forex Bureau, Microfinance Institutions, Sacco",
                  5.0, "5% of Selected Limit of Indemnity; excess Rwf250,000 or 10% of claim"))

    # 12. Directors & Officers liability (p32)
    conn.execute("CREATE TABLE directors_officers_liability(description_of_risk TEXT, rate_pct REAL)")
    conn.executemany("INSERT INTO directors_officers_liability VALUES(?,?)", [
        ("Financial Services (Banks, Forex Bureau, Microfinance Institutions, Sacco", 5.0),
        ("Other Risks such as offices not exposed to huge Sums of Money", 2.5),
    ])

    # 13. Money in transit / safe (p33-34)
    conn.execute("CREATE TABLE money_insurance(cover TEXT, rate_pct REAL, note TEXT)")
    labels, rows = _zip(MONEY_LABELS, seed.MONEY_RATES)
    conn.executemany("INSERT INTO money_insurance VALUES(?,?,?)",
                     [(lbl, r, n) for lbl, (_, r, _, n) in zip(labels, rows)])

    # 14. Money — annual carryings rate band (p33)
    conn.execute("""CREATE TABLE money_annual_carryings(
        sum_insured_band TEXT, rate_low_pct REAL, rate_high_pct REAL)""")
    labels, rows = _zip(MONEY_CARRYINGS_BANDS, seed.MONEY_CARRYINGS)
    conn.executemany("INSERT INTO money_annual_carryings VALUES(?,?,?)",
                     [(lbl, lo, hi) for lbl, (_, lo, hi, _) in zip(labels, rows)])

    # 15/16. Transit commodity grids (p36-44) — GIT and transporters liability
    transit_cols = """(code TEXT, commodity_classification TEXT,
        road_accident_containerized_pct REAL, road_accident_noncontainerized_pct REAL,
        all_risks_containerized_pct REAL, all_risks_noncontainerized_pct REAL, excess TEXT)"""
    for tbl in ("goods_in_transit", "transporters_liability"):
        conn.execute(f"CREATE TABLE {tbl} {transit_cols}")
        conn.executemany(f"INSERT INTO {tbl} VALUES(?,?,?,?,?,?,?)",
                         [(c, COMMODITY[c], a, b, d, e, x) for c, cm, a, b, d, e, x in seed.GIT])

    # 17-22. Liability suite + PA/GPA
    for tbl, col, labels, seed_rows in [
        ("public_liability", "occupation", PUBLIC_LIABILITY_LABELS, seed.PUBLIC_LIABILITY),
        ("employers_liability", "occupation", EMPLOYERS_LIABILITY_LABELS, seed.EMPLOYERS_LIABILITY),
        ("product_liability", "occupation", PRODUCT_LIABILITY_LABELS, seed.PRODUCT_LIABILITY),
        ("professional_indemnity", "profession", PROFESSIONAL_INDEMNITY_LABELS, seed.PROFESSIONAL_INDEMNITY),
        ("personal_accident_gpa", "risk_classification", PA_GPA_LABELS, seed.PA_GPA),
    ]:
        rate_col = "rate_pct" if tbl in ("professional_indemnity", "personal_accident_gpa") else "minimum_rate_pct"
        conn.execute(f"CREATE TABLE {tbl}({col} TEXT, {rate_col} REAL)")
        lbls, rows = _zip(labels, seed_rows)
        conn.executemany(f"INSERT INTO {tbl} VALUES(?,?)",
                         [(lbl, r) for lbl, (_, r) in zip(lbls, rows)])

    # 19. School liability fixed premiums (p47-48)
    conn.execute("""CREATE TABLE school_liability(
        school_category TEXT, annual_premium_rwf INTEGER,
        accidental_death_limit_rwf INTEGER, total_permanent_disability_limit_rwf INTEGER,
        medical_fees_limit_rwf INTEGER, third_party_liability_limit_rwf INTEGER)""")
    conn.executemany("INSERT INTO school_liability VALUES(?,?,?,?,?,?)", [
        ("Nursery and primary schools", 300, 1000000, 1000000, 100000, 1000000),
        ("Non-technical secondary schools", 1200, 2000000, 2000000, 200000, 2000000),
        ("Technical secondary schools", 1500, 2000000, 2000000, 200000, 2000000),
        ("Universities", 2000, 3000000, 3000000, 300000, 3000000),
    ])

    # 20/24. Short-period schedules for school & PA/GPA (p48/p52)
    sp_rows = [("Less or equal 3 Months Cover", 60),
               ("From 3 Months and 1 Day to 6 Months Cover", 80),
               ("From 6 Months and 1 Day to 12 Months Cover", 100)]
    for tbl in ("school_liability_short_period", "personal_accident_short_period"):
        conn.execute(f"CREATE TABLE {tbl}(short_period TEXT, rate_of_annual_premium_pct REAL)")
        conn.executemany(f"INSERT INTO {tbl} VALUES(?,?)", sp_rows)

    # 25/26. Erection & Contractors All Risks (p53-54, p62-63)
    for tbl in ("erection_all_risks", "contractors_all_risks"):
        conn.execute(f"CREATE TABLE {tbl}(risk_type TEXT, minimum_rate_pct REAL)")
        lbls, rows = _zip(EAR_CAR_LABELS, seed.EAR_CAR)
        conn.executemany(f"INSERT INTO {tbl} VALUES(?,?)",
                         [(lbl, r) for lbl, (_, r) in zip(lbls, rows)])

    # 27. Machinery breakdown (p55-56)
    conn.execute("CREATE TABLE machinery_breakdown(description_of_risk TEXT, material_damage_rate_pct REAL)")
    lbls, rows = _zip(MACHINERY_LABELS, seed.MACHINERY)
    conn.executemany("INSERT INTO machinery_breakdown VALUES(?,?)",
                     [(lbl, r) for lbl, (_, r) in zip(lbls, rows)])
    conn.execute("INSERT INTO machinery_breakdown VALUES(?,?)",
                 ("Machinery Insurance (Loss of Profits), excess 14 days", seed.MACHINERY_LOSS_OF_PROFITS))

    # 28. CPM — hazard class x plant group (p57)
    conn.execute("""CREATE TABLE cpm_rates(
        hazard_class TEXT, hazard_description TEXT,
        plant_group TEXT, plant_group_description TEXT, rate_pct REAL)""")
    hz = {"A": "Low hazard - level terrain, far from water hazards",
          "B": "Medium hazard - difficult terrain, close to water hazards",
          "C": "Very hazardous - difficult soil conditions, especially prone to acts of God"}
    pg = {"1": "Cranes - all types",
          "2": "Mobile plant - bulldozers, graders, loaders, excavators, etc.",
          "3": "Non-mobile plant - crushers, pumps, compressors, etc"}
    conn.executemany("INSERT INTO cpm_rates VALUES(?,?,?,?,?)",
                     [(cls, hz[cls], grp, pg[grp], rate) for (cls, grp), rate in seed.CPM.items()])

    # 29. CPM short-period (p57-58)
    conn.execute("CREATE TABLE cpm_short_period(short_period TEXT, rate_of_annual_premium_pct REAL)")
    conn.executemany("INSERT INTO cpm_short_period VALUES(?,?)", [
        ("From 1day to 1Month Cover", 50), ("From 1Month and 1day to 2Month Cover", 54),
        ("From 2Month and 1day to 3Month Cover", 59), ("From 3Month and 1day to 4Month Cover", 64),
        ("From 4Month and 1day to 5Month Cover", 68), ("From 5Month and 1day to 6Month Cover", 73),
        ("From 6Month and 1day to 12Month Cover", 100),
    ])

    # 30. Boilers & pressure vessels (p58)
    conn.execute("CREATE TABLE boilers_pressure_vessels(description_of_risk TEXT, rate_pct REAL, note TEXT)")
    conn.executemany("INSERT INTO boilers_pressure_vessels VALUES(?,?,?)", [
        ("Material Damage", 0.5, "Excess 10% of claim, min Rwf625,000"),
        ("Third Party Liability", 0.5, "Excess 10% of claim, min Rwf625,000"),
    ])

    # 31. Computer & electronic all risks (EEAR) (p58-59)
    conn.execute("CREATE TABLE eear_computer_all_risks(item TEXT, rate_pct REAL, note TEXT)")
    conn.executemany("INSERT INTO eear_computer_all_risks VALUES(?,?,?)", [
        ("Equipment at the insured's premises", 0.75, "Minimum rate; excess 10% min Rwf100,000"),
        ("Portable items away from the premises", 2.0, "Excess 10% min Rwf100,000"),
        ("Tender - items/values not specified (premises vs away)", 1.5, "Rate to apply 1.5%"),
        ("Increased Cost of Working (data reconstruction)", 0.75, "Excess 10% min Rwf100,000"),
    ])

    # 32. Aviation (p64)
    conn.execute("CREATE TABLE aviation(description_of_risk TEXT, rate_pct REAL, note TEXT)")
    conn.executemany("INSERT INTO aviation VALUES(?,?,?)", [
        ("Hull All Risks", 0.15, "0.15% of Hull Value"),
        ("Cargo (low end)", 0.175, "0.175% - 0.25% depending on nature of cargo"),
        ("Cargo (high end)", 0.25, "0.175% - 0.25% depending on nature of cargo"),
        ("Airport Operators Liability", 0.2, "0.2% of Selected limit of indemnity"),
        ("Hanger Keeper Liability", 0.2, "0.2%; exclude professional negligence and defective spare parts"),
        ("PAX Liability (Passenger)", 0.185, "0.185% of indemnity limit per seat; exclude non fare paying passengers"),
        ("Crew", None, "Normal GPA rates apply but loaded by 25% for Occupational Hazard"),
    ])

    # 33. Marine hull (p65-66)
    conn.execute("CREATE TABLE marine_hull(insured_risk TEXT, rate_pct REAL, note TEXT)")
    conn.executemany("INSERT INTO marine_hull VALUES(?,?,?)", [
        ("The hull (Hull All Risks)", 0.8, "Value of the vessel X 0.8%"),
        ("Liability for boat", 0.25, "TPL property: per-event 50m / annual 500m; bodily: per-person 5m / event 25m / annual 200m"),
    ])

    # 34. Marine hull — per-occupant bodily-injury premiums (p66)
    conn.execute("""CREATE TABLE marine_hull_occupant_premiums(
        tier TEXT, death_sum_rwf INTEGER, permanent_disablement_sum_rwf INTEGER,
        medical_fees_sum_rwf INTEGER, net_premium_rwf INTEGER)""")
    conn.executemany("INSERT INTO marine_hull_occupant_premiums VALUES(?,?,?,?,?)", [
        ("I", 1000000, 1000000, 100000, 6250),
        ("II", 2000000, 2000000, 200000, 7500),
        ("III", 3000000, 3000000, 300000, 11250),
        ("IV", 4000000, 4000000, 400000, 18000),
        ("V", 5000000, 5000000, 500000, 18750),
    ])

    # 35. Marine cargo ICC-A commodity grid (p67-69)
    conn.execute("""CREATE TABLE marine_cargo(code TEXT, commodity_classification TEXT,
        icca_containerized_pct REAL, icca_noncontainerized_pct REAL, excess TEXT)""")
    conn.executemany("INSERT INTO marine_cargo VALUES(?,?,?,?,?)",
                     [(c, COMMODITY[c], d, e, x) for c, cm, _, _, d, e, x in seed.MARINE_CARGO])

    # 36. Bonds / guarantees (p70)
    conn.execute("CREATE TABLE bonds_guarantees(description_of_bond TEXT, rate_pct REAL)")
    lbls, rows = _zip(BONDS_LABELS, seed.BONDS)
    conn.executemany("INSERT INTO bonds_guarantees VALUES(?,?)",
                     [(lbl, r) for lbl, (_, r) in zip(lbls, rows)])

    # 37. Fidelity guarantee (p71)
    conn.execute("CREATE TABLE fidelity_guarantee(description_of_risk TEXT, rate_pct REAL)")
    lbls, rows = _zip(FIDELITY_LABELS, seed.FIDELITY)
    conn.executemany("INSERT INTO fidelity_guarantee VALUES(?,?)",
                     [(lbl, r) for lbl, (_, r) in zip(lbls, rows)])

    # 38. PVT — political violence & terrorism (per mille!) (p72-73)
    conn.execute("""CREATE TABLE pvt_political_violence_terrorism(
        description_of_risk TEXT, rate_per_mille REAL, proposed_deductible TEXT)""")
    conn.executemany("INSERT INTO pvt_political_violence_terrorism VALUES(?,?,?)", [
        ("Private Stand-alone Residence", 0.60, "5% e.e.l min 0.5% of SI (Amount)"),
        ("Apartments", 0.65, "5% e.e.l min 0.5% of SI (Amount)"),
        ("Administrative Offices", 0.80, "5% e.e.l min 0.5% of SI (Amount)"),
        ("Commercial Building in own compound", 1.00, "5% e.e.l min 0.5% of SI (Amount)"),
        ("Commercial Building not protected by boundary wall", 1.10, "5% e.e.l min 0.5% of SI (Amount)"),
        ("Hotels / Banks", 1.50, "5% e.e.l min 0.5% of SI (Amount)"),
        ("Industrial Risks in own compound with electric fence", 1.00, "5% e.e.l min 0.5% of SI (Amount)"),
        ("Industrial Risks without boundary wall", 1.10, "5% e.e.l min 0.5% of SI (Amount)"),
        ("Roadside Shops", None, "NO QUOTE"),
        ("Supermarkets protected by access control", 1.80, "5% e.e.l min 0.5% of SI (Amount)"),
        ("Churches, Mosques, Temples", 1.00, "5% e.e.l min 0.5% of SI (Amount)"),
    ])

    # 39. Plate glass (p22)
    conn.execute("CREATE TABLE plate_glass(cover TEXT, minimum_rate_pct REAL, note TEXT)")
    conn.execute("INSERT INTO plate_glass VALUES(?,?,?)",
                 ("Plate Glass", 2.0, "Mandatory excess 5% each loss, min Rwf100,000"))

    # Consequential Loss - Dual Basis Wages Cover matrix (p26)
    conn.execute("""CREATE TABLE consequential_loss_dual_basis_wages(
        indemnity_period_months INTEGER, initial_period_weeks INTEGER,
        wage_pct_insured REAL, pct_of_basis_rate REAL,
        alternative_insurance_weeks INTEGER)""")
    _dbw = []
    for months, weeks, vals in DUAL_BASIS_WAGES:
        for i, wp in enumerate(DUAL_BASIS_WAGE_PCTS):
            _dbw.append((months, weeks, wp, vals[2 * i], vals[2 * i + 1]))
    conn.executemany(
        "INSERT INTO consequential_loss_dual_basis_wages VALUES(?,?,?,?,?)", _dbw)

    # 40-42. Large-risk registers (p76-80)
    for tbl, rows in [("large_risks_property", LARGE_RISKS_PROPERTY),
                      ("large_risks_engineering", LARGE_RISKS_ENGINEERING),
                      ("large_risks_accident", LARGE_RISKS_ACCIDENT)]:
        conn.execute(f"CREATE TABLE {tbl}(property TEXT, insured_value_rwf INTEGER)")
        conn.executemany(f"INSERT INTO {tbl} VALUES(?,?)", rows)

    # 43. Market-wide parameters (each row carries its own unit)
    conn.execute("CREATE TABLE market_parameters(parameter TEXT, value REAL, unit TEXT, note TEXT)")
    conn.executemany("INSERT INTO market_parameters VALUES(?,?,?,?)", MARKET_PARAMETERS)

    # 44. Minimum premiums by class
    conn.execute("CREATE TABLE minimum_premiums(insurance_class TEXT, minimum_premium_rwf INTEGER, note TEXT)")
    conn.executemany("INSERT INTO minimum_premiums VALUES(?,?,?)", MINIMUM_PREMIUMS)

    # 45. Data dictionary — documents the UNIT of every column so users/agents
    # never have to guess whether a number is a %, per-mille, or RWF amount.
    conn.execute("""CREATE TABLE data_dictionary(
        table_name TEXT, column_name TEXT, unit TEXT, description TEXT)""")
    dict_rows = []
    existing = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name != 'data_dictionary'"
        " ORDER BY name").fetchall()]
    for t in existing:
        for col in conn.execute(f"PRAGMA table_info({t})").fetchall():
            name, ctype = col[1], col[2]
            unit, desc = _unit_for(t, name, ctype)
            dict_rows.append((t, name, unit, desc))
    conn.executemany("INSERT INTO data_dictionary VALUES(?,?,?,?)", dict_rows)

    conn.commit()

    tables = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    total = 0
    print(f"Built {db_path}\n{len(tables)} tables:")
    for t in tables:
        n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        total += n
        print(f"  {t:42s} {n:>4d} rows")
    print(f"  {'TOTAL':42s} {total:>4d} rows")
    conn.close()


def print_schema(db_path: Path = DB_PATH) -> None:
    """Print a data dictionary (table + columns) for the text-to-SQL agent."""
    conn = sqlite3.connect(str(db_path))
    names = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
    for t in names:
        cols = [f"{r[1]} {r[2]}" for r in conn.execute(f"PRAGMA table_info({t})").fetchall()]
        print(f"{t}({', '.join(cols)})")
    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build the ASSAR information-engine DB.")
    ap.add_argument("--schema", action="store_true", help="print the table/column catalog and exit")
    args = ap.parse_args()
    if args.schema:
        print_schema()
    else:
        build()
