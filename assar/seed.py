"""Rate data transcribed from the ASSAR General Business Pricing Manual, Version 3
(issue date 2021-01-25). All percentage rates are stored as percent values
(e.g. 0.150 means 0.150%). PVT is stored in per_mille — see UNIT note below.

!! VERIFY BEFORE PRODUCTION USE !!
These figures were transcribed from the PDF. Spot-check against the source manual
before pricing live business; a wrong cell here is a real underwriting error.
"""

# ---------------------------------------------------------------------------
# Special perils (rate per peril) — commercial/industrial vs residential
# ---------------------------------------------------------------------------
SPECIAL_PERILS = [
    # (category, commercial/industrial %, residential %)
    ("earthquake",                 0.0120, 0.0060),
    ("storm_tempest_flood_tornado",0.0600, 0.0600),
    ("riot_strike",                0.0060, 0.0060),
    ("malicious_damage",           0.0090, 0.0030),
    ("burst_pipe_water_damage",    0.0006, 0.0006),
    ("impact",                     0.0006, 0.0006),
    ("bush_fire",                  0.0012, 0.0006),
    ("subsidence",                 0.0600, 0.0600),
    ("spontaneous_combustion",     0.0150, 0.0120),
    # full_explosion already covered under standard fire policy
]

# ---------------------------------------------------------------------------
# Fire & Allied Perils — Commercial/Administrative (Material Damage)
# (risk category, standard fire %, fire + all special perils %)
# ---------------------------------------------------------------------------
FIRE = [
    ("aerated_water_mineral_water_treatment_plant", 0.150, 0.3144),
    ("agricultural_show_grounds",                   0.180, 0.3444),
    ("airports_airfields_hangers",                  0.150, 0.3144),
    ("aluminum_pressing_works",                     0.150, 0.3144),
    ("auction_sale_rooms",                          0.150, 0.3144),
    ("automobile_show_rooms",                       0.150, 0.3144),
    ("bacon_factories",                             0.180, 0.3444),
    ("bakeries_biscuits",                           0.180, 0.3444),
    ("banks",                                       0.125, 0.2000),
    ("bars_gaming_rooms",                           0.180, 0.3444),
    ("blacksmiths",                                 0.240, 0.4044),
    ("boarding_houses",                             0.150, 0.3144),
    ("boat_houses",                                 0.150, 0.3144),
    ("boot_shoe_factories",                         0.180, 0.3444),
    ("brick_tile_works",                            0.150, 0.3144),
    ("broadcasting_telecom_houses",                 0.150, 0.3144),
    ("buildings_under_construction",                0.150, 0.3144),
    ("butter_cheese_creameries_dairies",            0.150, 0.3144),
    ("cafes_restaurants",                           0.150, 0.3144),
    ("candle_manufacturing",                        0.240, 0.4044),
    ("car_bonds_warehouses",                        0.150, 0.3144),
    ("ceramic_pottery_works",                       0.180, 0.3444),
    ("chemical_insecticides_sprays",                0.180, 0.3444),
    ("chemical_manufacturing_storage",              0.180, 0.3444),
    ("churches_chapels_mosques_temples",            0.125, 0.2000),
    ("cigarette_factories",                         0.240, 0.4044),
    ("cinemas_theatres",                            0.150, 0.3144),
    ("clothing_factories",                          0.180, 0.3444),
    ("clubs_discotheques",                          0.180, 0.3444),
    ("coal_compost_manure_open",                    0.300, 0.4644),
    ("coffee_mills_factories",                      0.150, 0.3144),
    ("cold_storage_ice_factories",                  0.150, 0.3144),
    ("collieries",                                  0.240, 0.4044),
    ("concrete_block_works_cement_plant",           0.150, 0.3144),
    ("confectioneries_manufacturing",               0.150, 0.3144),
    ("cosmetic_factories",                          0.180, 0.3444),
    ("cotton_factories",                            0.180, 0.3444),
    ("distilleries_chemical",                       0.150, 0.3144),
    ("dry_cleaners",                                0.150, 0.3144),
    ("dwellings_domestic_outbuildings_apartment",   0.150, 0.3144),
    ("electric_light_power_stations",               0.150, 0.3144),
    ("engineering_workshops",                       0.150, 0.3144),
    ("fish_meat_processing",                        0.150, 0.3144),
    ("flax_factories",                              0.300, 0.4644),
    ("flour_mealie_mills",                          0.150, 0.3144),
    ("fruit_juice_factories",                       0.150, 0.3144),
    ("garages",                                     0.150, 0.3144),
    ("ghee_refineries",                             0.180, 0.3444),
    ("glass_factories",                             0.180, 0.3444),
    ("gold_smiths",                                 0.180, 0.3444),
    ("goods_in_bonded_warehouses",                  0.180, 0.3444),
    ("goods_in_open_not_provided_for",              0.180, 0.3444),
    ("grass_papyrus_makuti_thatched_buildings",     0.360, 0.5244),
    # green_houses -> refer to reinsurers' rate
    ("hospitals",                                   0.125, 0.2000),
    ("hotels",                                      0.125, 0.2200),
    ("jaggery_industries",                          0.180, 0.3444),
    ("jam_canning_factories",                       0.150, 0.3144),
    ("knitting_works",                              0.180, 0.3444),
    ("joinery",                                     0.180, 0.3444),
    ("laundries",                                   0.150, 0.3144),
    ("masonic_fraternal_meeting_halls",             0.125, 0.2000),
    ("match_manufacturing",                         0.240, 0.4044),
    ("mining_risks",                                0.150, 0.3144),
    ("nail_screw_needle_wire_makers",               0.150, 0.3144),
    ("offices",                                     0.125, 0.2000),
    ("oil_storage_depots_petrol_gas",               0.240, 0.4044),
    ("oil_petrol_gas_fat_factories",                0.150, 0.3144),
    ("power_houses_hydro_peat_plant",               0.150, 0.3144),
    ("paint_varnish_factories",                     0.240, 0.4044),
    ("paper_industries",                            0.180, 0.3444),
    ("petrol_gas_filling_stations",                 0.150, 0.3144),
    ("pharmaceutical_tablet_pill_bottle",           0.150, 0.3144),
    ("plastic_industries",                          0.240, 0.4044),
    ("poultry_houses",                              0.150, 0.3144),
    ("printing_works_carton_factories",             0.150, 0.3144),
    ("pyrethrum_drying_sheds",                      0.300, 0.4644),
    ("quarries",                                    0.150, 0.3144),
    ("razor_blade_makers",                          0.150, 0.3144),
    ("rice_mills",                                  0.150, 0.3144),
    ("rubber_tyre_factories_retreading",            0.180, 0.3444),
    ("schools_day",                                 0.125, 0.2200),
    ("schools_colleges_boarding_hostels",           0.150, 0.2500),
    ("shops_supermarkets_markets_malls",            0.150, 0.3144),
    ("silent_dormant_risks",                        0.150, 0.3144),
    ("sisal_factories",                             0.240, 0.4044),
    ("soap_factories",                              0.150, 0.3144),
    ("spray_painting",                              0.180, 0.3444),
    ("stables",                                     0.150, 0.3144),
    ("steel_tubes_bed_furniture_makers",            0.150, 0.3144),
    ("steel_rolling_mills_bar_girder",              0.150, 0.3144),
    ("sugar_mills_refinery",                        0.150, 0.3144),
    ("tanneries",                                   0.150, 0.3144),
    ("tea_factories_withering_houses",              0.150, 0.3144),
    ("timber_stores_sheds_strong",                  0.180, 0.3444),
    ("tobacco_factories",                           0.240, 0.4044),
    ("unoccupied_buildings",                        0.150, 0.3144),
    ("vinegar_factories",                           0.150, 0.3144),
    ("wattle_extract_factories",                    0.240, 0.4044),
    ("wattle_dry_back_factories",                   0.240, 0.4044),
    ("wine_bottling_premises",                      0.150, 0.3144),
    ("woodworkers_carpenters_saw_mills",            0.180, 0.3444),
    ("thatched_roof_buildings",                     0.450, 0.6144),
    ("other_occupancy_not_specified",               0.450, 0.6144),
    # Private dwellings (all perils inclusive): buildings & contents 0.15;
    # fire/lightning/explosion only -> 0.12
    ("private_dwelling_buildings",                  0.150, 0.150),
    ("private_dwelling_contents",                   0.150, 0.150),
]
FIRE_ONLY_DWELLING = 0.12   # private dwelling, fire/lightning/explosion only

# ---------------------------------------------------------------------------
# Transit rates — GIT and Marine Cargo
# GIT  (page 36): all-risks = ICC-A discounted 10%, road-accident = ICC-C discounted 10%
# Marine cargo (page 67): ICC-A is the base (combined modes)
# (code, commodity, ra_cont, ra_noncont, ar_cont, ar_noncont, excess)
# ---------------------------------------------------------------------------
GIT = [
    ("1.a", "raw_agricultural_produce", 0.204750, 0.2252250, 0.3150, 0.34650, "1% of consignment, min Rwf250,000"),
    ("1.b", "grains_in_bags",           0.219375, 0.2413125, 0.3375, 0.37125, "1% of consignment, min Rwf250,000"),
    ("2.a", "nonfragile_not_pilferable",0.204750, 0.2252250, 0.3150, 0.34650, "1% of consignment, min Rwf250,000"),
    ("2.b", "nonfragile_pilferable",    0.219375, 0.2413125, 0.3375, 0.37125, "5% of adjusted claim, min Rwf250,000"),
    ("3",   "semi_fragile",             0.321750, 0.3539250, 0.4950, 0.54450, "5% of adjusted claim, min Rwf250,000"),
    ("4",   "fragile",                  0.877500, 0.9652500, 1.3500, 1.48500, "5% of adjusted claim, min Rwf250,000"),
    ("5.a", "chemical_in_drums",        0.263250, 0.2895750, 0.4050, 0.44550, "5% of adjusted claim, min Rwf250,000"),
    ("5.b", "chemicals_cement_fertilizer_bags", 0.351000, 0.3861000, 0.5400, 0.59400, "5% of adjusted claim, min Rwf250,000"),
    ("5.c", "pharmaceuticals",          0.380250, 0.4182750, 0.5850, 0.64350, "5% of adjusted claim, min Rwf250,000"),
    ("6.a", "food_confectionery_cans",  0.204750, 0.2252250, 0.3150, 0.34650, "5% of adjusted claim, min Rwf250,000"),
    ("6.b", "food_confectionery_bags",  0.219375, 0.2413125, 0.3375, 0.37125, "5% of adjusted claim, min Rwf250,000"),
    ("7.a", "bulk_petroleum",           0.438750, 0.4826250, 0.6750, None,    "Subject to Institute Bulk Oil Clauses/Cover B"),
    ("7.b", "bulk_grains_edible_oils",  0.204750, 0.2252250, 0.3150, None,    "1% of consignment, min Rwf250,000"),
    ("7.c", "other_liquid_beers",       0.877500, 0.9652500, 1.3500, None,    "1% of consignment, min Rwf250,000"),
    ("8",   "matches_fireworks_explosives", 0.731250, 0.8043750, 1.1250, 1.23750, "5% of adjusted claim, min Rwf500,000"),
    ("9",   "copper_precious_metals",   0.731250, 0.8043750, 1.1250, 1.23750, "5% of adjusted claim, min Rwf500,000"),
    ("10.a","household_professionally_packed", 0.292500, 0.3217500, 0.4500, 0.49500, "5% of adjusted claim, min Rwf500,000"),
    ("10.b","household_not_professionally_packed", 0.438750, 0.4826250, 0.6750, 0.74250, "5% of adjusted claim, min Rwf500,000"),
]

# Marine cargo ICC-A (containerized, non-containerized). Road accident columns
# left None — marine cargo is rated off ICC-A with mode discounts applied in code.
MARINE_CARGO = [
    ("1.a", "raw_agricultural_produce", None, None, 0.350, 0.3850, "1% of consignment, min Rwf250,000"),
    ("1.b", "grains_in_bags",           None, None, 0.375, 0.4125, "1% of consignment, min Rwf250,000"),
    ("2.a", "nonfragile_not_pilferable",None, None, 0.350, 0.3850, "1% of consignment, min Rwf250,000"),
    ("2.b", "nonfragile_pilferable",    None, None, 0.375, 0.4125, "5% of adjusted claim, min Rwf250,000"),
    ("3",   "semi_fragile",             None, None, 0.550, 0.6050, "5% of adjusted claim, min Rwf250,000"),
    ("4",   "fragile",                  None, None, 1.500, 1.6500, "5% of adjusted claim, min Rwf250,000"),
    ("5.a", "chemical_in_drums",        None, None, 0.450, 0.4950, "5% of adjusted claim, min Rwf250,000"),
    ("5.b", "chemicals_cement_fertilizer_bags", None, None, 0.600, 0.6600, "5% of adjusted claim, min Rwf250,000"),
    ("5.c", "pharmaceuticals",          None, None, 0.650, 0.7150, "5% of adjusted claim, min Rwf250,000"),
    ("6.a", "food_confectionery_cans",  None, None, 0.350, 0.3850, "5% of adjusted claim, min Rwf250,000"),
    ("6.b", "food_confectionery_bags",  None, None, 0.375, 0.4125, "5% of adjusted claim, min Rwf250,000"),
    ("7.a", "bulk_petroleum",           None, None, 0.750, None,   "Subject to Institute Bulk Oil Clauses/Cover B"),
    ("7.b", "bulk_grains_edible_oils",  None, None, 0.350, None,   "1% of consignment, min Rwf250,000"),
    ("7.c", "other_liquid_beers",       None, None, 1.500, None,   "1% of consignment, min Rwf250,000"),
    ("8",   "matches_fireworks_explosives", None, None, 1.250, 1.3750, "5% of adjusted claim, min Rwf500,000"),
    ("9",   "copper_precious_metals",   None, None, 1.250, 1.3750, "5% of adjusted claim, min Rwf500,000"),
    ("10.a","household_professionally_packed", None, None, 0.500, 0.5500, "5% of adjusted claim, min Rwf500,000"),
    ("10.b","household_not_professionally_packed", None, None, 0.750, 0.8250, "5% of adjusted claim, min Rwf500,000"),
]

# ---------------------------------------------------------------------------
# Liability suite (rate on selected limit of indemnity)
# ---------------------------------------------------------------------------
PUBLIC_LIABILITY = [
    ("utilities", 2.00), ("manufacturing", 0.80), ("hotel_restaurant_tourism", 0.40),
    ("telecom_financial_services", 0.20), ("chemical_industries", 1.20), ("others", 0.20),
]
EMPLOYERS_LIABILITY = [
    ("businessmen", 0.250), ("engineers", 0.350), ("office_administration", 0.185),
    ("manufacturing_non_hazardous", 0.250), ("manufacturing_hazardous", 0.350),
    ("construction_workers", 0.350), ("drivers_security_mining", 0.500),
]
PRODUCT_LIABILITY = [
    ("manufacturing_human_food", 0.40), ("manufacturing_electronics_construction", 0.30),
    ("chemical_industries", 0.30), ("others", 0.20),
]
PROFESSIONAL_INDEMNITY = [
    ("medical_malpractice", 3.00), ("engineers_architects_builders", 2.50),
    ("lawyers_accountants_auditors_surveyors", 2.00), ("insurance_agents", 1.50), ("others", 1.50),
]

# ---------------------------------------------------------------------------
# Personal Accident / Group Personal Accident (rate; death=TPD=rate)
# ---------------------------------------------------------------------------
PA_GPA = [
    ("businessmen", 0.250), ("engineers", 0.350), ("office_administration", 0.185),
    ("manufacturing_non_hazardous", 0.250), ("manufacturing_hazardous", 0.350),
    ("construction_workers", 0.350), ("drivers_security_mining", 0.500),
    ("student_internship", 0.250),
]

# ---------------------------------------------------------------------------
# Bonds / Guarantees (full rate, no short period). 100% cash collateral -> 3%.
# ---------------------------------------------------------------------------
BONDS = [
    ("performance_bond", 5.0), ("advance_payment_bond", 5.0), ("financial_guarantee", 5.0),
    ("bid_bond", 2.0), ("customs_bond_rctg", 0.4), ("bonded_warehouse", 0.5),
    ("temporary_importation", 3.0),
]

# ---------------------------------------------------------------------------
# Fidelity Guarantee
# ---------------------------------------------------------------------------
FIDELITY = [
    ("financial_services", 4.5), ("distribution_sales_purchasing", 4.0),
    ("other_offices", 2.5), ("security_firms", 5.0),
]

# BBB and D&O
BBB = [("financial_services", 5.0)]
DO_LIABILITY = [("financial_services", 5.0), ("other_offices", 2.5)]

# ---------------------------------------------------------------------------
# PVT — Political Violence & Terrorism. RATES ARE PER MILLE (not percent!)
# ---------------------------------------------------------------------------
PVT = [
    ("private_standalone_residence", 0.60), ("apartments", 0.65),
    ("administrative_offices", 0.80), ("commercial_in_own_compound", 1.00),
    ("commercial_no_boundary_wall", 1.10), ("hotels_banks", 1.50),
    ("industrial_own_compound_electric_fence", 1.00), ("industrial_no_boundary_wall", 1.10),
    # roadside_shops -> NO QUOTE
    ("supermarkets_access_control", 1.80), ("churches_mosques_temples", 1.00),
]

# ---------------------------------------------------------------------------
# Engineering — EAR / CAR (identical project-type list)
# ---------------------------------------------------------------------------
EAR_CAR = [
    ("residential_buildings", 0.2), ("commercial_administrative_buildings", 0.225),
    ("water_tanks", 0.25), ("water_pipelines", 0.275),
    ("power_transmission_public_lighting", 0.350), ("excavation_works", 0.3),
    ("stadium", 0.275), ("bridges", 0.35), ("dams", 0.5), ("petroleum_tank_farms", 0.45),
    ("roads_urban", 0.3), ("roads_rural", 0.35), ("roads_open_area_paving", 0.275),
    ("airports", 0.325), ("ports", 0.55), ("power_plant_genset", 0.275),
    ("power_plant_hydroelectric", 0.125), ("power_plant_gas_turbines", 0.275),
    ("power_plant_geothermal", 0.30), ("power_plant_coal", 0.30),
    ("power_plant_flywheel_storage", 0.175), ("power_plant_hybrid", 0.30),
    ("power_plant_combined_cycle_gas", 0.275), ("power_plant_wind_farm", 0.125),
    ("power_plant_solar", 0.125), ("communication_towers", 0.275),
]
EAR_CAR_TPL_SEPARATE = 0.2  # used when TPL limit exceeds 15% of project value

# Machinery breakdown (material damage rate)
MACHINERY = [
    ("combine_harvester", 2.0), ("crawler_caterpillar", 3.0), ("fodder_drying_straw_baling", 0.8),
    ("leather_industry", 0.8), ("paper_cardboard", 0.8), ("cold_storage_chillers_freezer", 0.7),
    ("wood_working", 1.25), ("residence_office_hospital", 0.6), ("cinema_film_projectors", 1.25),
    ("food_fodder_industry", 0.6), ("metal_producing", 1.0), ("electrical_smelting_furnace", 1.0),
    ("scrap_shearer", 2.0), ("metal_riveting_welding", 1.0), ("metal_cutting_facing", 0.5),
    ("forging_hot_work", 2.0), ("forging_cold_work", 1.0), ("rolling_mill", 0.8),
    ("heat_treatment_wire_drawing", 1.0), ("chemical_injection_molding", 0.8),
    ("chemical_other_machines", 0.4), ("graphic_industry", 0.5), ("mining_surface", 2.0),
    ("transport_traffic_system", 0.8), ("conveyors_cranes_winches_cpm", 1.0),
    ("transformers", 3.0), ("others", 0.5),
]
MACHINERY_LOSS_OF_PROFITS = 0.75  # excess 14 days

# CPM — Contractors Plant & Machinery: hazard class (A/B/C) x plant group (1/2/3)
CPM = {
    ("A", "1"): 1.20, ("A", "2"): 0.80, ("A", "3"): 0.40,
    ("B", "1"): 1.50, ("B", "2"): 1.10, ("B", "3"): 0.60,
    ("C", "1"): 1.80, ("C", "2"): 1.50, ("C", "3"): 0.90,
}

# Misc single rates
PLATE_GLASS = 2.0
BOILER_MD = 0.5
BOILER_TPL = 0.5
EEAR_PREMISES = 0.75
EEAR_PORTABLE = 2.0
EEAR_UNSPECIFIED = 1.5
EEAR_ICOW = 0.75
MONEY_SINGLE_TRIP = 0.3
MONEY_IN_SAFE = 0.275
MONEY_IN_ATM = 0.275
AVIATION = {
    "hull_all_risks": 0.15, "cargo_low": 0.175, "cargo_high": 0.25,
    "airport_operators_liability": 0.2, "hanger_keeper_liability": 0.2,
    "pax_liability_per_seat": 0.185,
}
MARINE_HULL = 0.8
MARINE_HULL_TPL = 0.25

# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------
# Voluntary deductible discount (cap: saving <= 33.33% of the excess amount)
VOLUNTARY_DEDUCTIBLE = [
    (0,        250_000,   "up to 250,000",        5.0),
    (250_000,  500_000,   "250,000 - 500,000",    7.5),
    (500_000,  1_000_000, "500,000 - 1,000,000",  10.0),
    (1_000_000,2_000_000, "1,000,000 - 2,000,000",12.5),
    (2_000_000,3_000_000, "2,000,000 - 3,000,000",15.0),
    (3_000_000,4_000_000, "3,000,000 - 4,000,000",17.5),
    (4_000_000,5_000_000, "4,000,000 - 5,000,000",20.0),
]
VOLUNTARY_DEDUCTIBLE_CAP = 33.33  # % of the excess amount

# Standard short-period scale -> fraction of annual premium (in months)
SHORT_PERIOD_STANDARD = [
    (0,    1/24, "1 day"),      # handled specially by days in code; months bands below
]
# Stored by months for the generic case:
SHORT_PERIOD_MONTHS = [
    (1,  0.25,  "1 month"),
    (2,  0.375, "2 months"),
    (3,  0.5,   "3 months"),
    (4,  0.625, "4 months"),
    (6,  0.75,  "6 months"),
    (8,  0.875, "8 months"),
    (12, 1.0,   "over 8 months / annual"),
]
SHORT_PERIOD_DAYS = [
    (1, 1/24, "1 day"), (3, 1/12, "3 days"), (7, 1/8, "1 week"),
]
SHORT_PERIOD_SCHOOL = [(3, 0.60, "<=3 months"), (6, 0.80, "3-6 months"), (12, 1.0, "6-12 months")]
SHORT_PERIOD_PA_GPA = SHORT_PERIOD_SCHOOL
SHORT_PERIOD_CPM = [
    (1, 0.50, "1 day - 1 month"), (2, 0.54, "1-2 months"), (3, 0.59, "2-3 months"),
    (4, 0.64, "3-4 months"), (5, 0.68, "4-5 months"), (6, 0.73, "5-6 months"),
    (12, 1.00, "6-12 months"),
]

# Consequential loss: indemnity-period multiplier (% of basis rate) by months
CI_INDEMNITY = [
    (3, 75), (4, 90), (6, 110), (9, 130), (12, 150), (15, 145), (18, 140),
    (24, 125), (30, 120), (36, 115), (48, 110), (60, 105), (72, 100), (999, 95),
]
CI_VOLUNTARY_TIME_EXCESS = [  # days -> discount %
    (20, 7.5), (30, 10.0), (40, 12.5), (50, 15.0), (60, 17.5), (90, 20.0),
]
MB_VOLUNTARY_TIME_EXCESS = CI_VOLUNTARY_TIME_EXCESS  # same schedule for machinery BI

# Burglary first-loss multipliers (ratio of first-loss SI to full value -> multiplier %)
FIRST_LOSS = [
    (0.25, 50), (0.30, 60), (0.35, 70), (0.45, 80), (0.50, 90), (1.0, 100),
]

# ---------------------------------------------------------------------------
# Per-product rules (minimum premiums net of taxes/fees, mandatory excesses)
# ---------------------------------------------------------------------------
PRODUCT_RULES = {
    "global":               {"policy_fee": 5_000, "commission_lead": 25.0},
    "fire":                 {"industrial_load": 0.025, "industrial_ext_load": 25_000, "fea_discount": 15.0},
    "money":                {"min_premium": 200_000, "excess_pct": 10.0, "excess_min": 200_000},
    "public_liability":     {"min_premium": 100_000},
    "employers_liability":  {"min_premium": 100_000},
    "product_liability":    {"min_premium": 100_000},
    "professional_indemnity":{"min_premium": 200_000, "min_premium_agents": 25_000,
                              "excess_pct": 5.0, "excess_min": 200_000},
    "pa":                   {"min_premium": 25_000, "min_premium_student": 15_000},
    "gpa":                  {"min_premium": 50_000, "min_premium_student": 30_000},
    "bond":                 {"min_premium_bid": 10_000, "min_premium_other": 30_000,
                              "cash_collateral_rate": 3.0},
    "fidelity":             {"min_premium": 200_000, "blanket_per_capita": 30_000,
                              "excess_min": 250_000, "excess_pct": 10.0},
    "bbb":                  {"excess_min": 250_000, "excess_pct": 10.0},
    "do_liability":         {"excess_min": 250_000, "excess_pct": 10.0},
    "pvt":                  {"excess_pct": 5.0, "excess_min_pct_si": 0.5, "excess_min": 50_000,
                             "max_retention_pct": 5.0},
    "burglary":             {"excess_pct": 10.0, "excess_min": 50_000, "stock_declaration_discount": 10.0},
    "plate_glass":          {"excess_pct": 5.0, "excess_min": 100_000},
    "machinery":            {"excess_pct_large": 10.0, "excess_min_large": 500_000,
                             "excess_pct_small": 5.0, "excess_min_small": 250_000,
                             "large_si_threshold": 5_000_000},
    "cpm":                  {"excess_pct": 10.0, "excess_min": 500_000},
    "eear":                 {"excess_pct": 10.0, "excess_min": 100_000},
    "boiler":               {"excess_pct": 10.0, "excess_min": 625_000},
    "ear":                  {"tpl_pct_cap": 15.0, "extension_load_per_6mo": 25.0},
    "car":                  {"tpl_pct_cap": 15.0, "extension_load_per_6mo": 25.0},
    "consequential_loss":   {"gross_profit_pct": 150.0, "auditors_fees_pct": 125.0,
                             "wages_pct": 100.0, "mandatory_time_excess_days": 14},
}


# ===========================================================================
# Additional rate tables (added to complete DB coverage of the manual)
# ===========================================================================

# --- Money & Cash in Transit (page 33-34) ---------------------------------
# rows: (category, rate, rate_alt, note). out_of_safe / personal_custody are
# 150% of the in-safe rate (0.275% -> 0.4125%).
MONEY_RATES = [
    ("single_trip",              0.3,    None, "% of single trip value"),
    ("in_safe_strongroom",       0.275,  None, "% of limit"),
    ("in_atm_machine",           0.275,  None, "% of limit"),
    ("out_of_safe",              0.4125, None, "150% of in-safe/strongroom rate"),
    ("personal_custody_senior",  0.4125, None, "150% of in-safe/strongroom rate"),
    ("safe_or_atm_itself",       0.275,  None, "% of value of the safe / ATM machine"),
]
# Annual carryings: rate is a RANGE -> rate=low, rate_alt=high (% )
MONEY_CARRYINGS = [
    ("carryings_0_to_10bn",   0.025,  0.05,  "Annual carryings, sum insured 0 < 10 BN"),
    ("carryings_10_to_15bn",  0.0225, 0.045, "Annual carryings, 10 < 15 BN"),
    ("carryings_15_to_20bn",  0.02,   0.04,  "Annual carryings, 15 < 20 BN"),
    ("carryings_20_to_30bn",  0.0175, 0.035, "Annual carryings, 20 < 30 BN"),
    ("carryings_30_to_50bn",  0.015,  0.03,  "Annual carryings, 30 < 50 BN"),
    ("carryings_above_50bn",  0.01,   0.02,  "Annual carryings, above 50 BN"),
]

# --- School Liability fixed premiums (page 47-48) -------------------------
# Flat premium per student, annual, inclusive of fees & VAT. (category, amount, note)
SCHOOL_LIABILITY = [
    ("nursery_primary",          300,  "Per student. Limits: death 1,000,000 / TPD 1,000,000 / medical 100,000 / TPL 1,000,000"),
    ("secondary_non_technical", 1200,  "Per student. Limits: death 2,000,000 / TPD 2,000,000 / medical 200,000 / TPL 2,000,000"),
    ("secondary_technical",     1500,  "Per student. Limits: death 2,000,000 / TPD 2,000,000 / medical 200,000 / TPL 2,000,000"),
    ("university",              2000,  "Per student. Limits: death 3,000,000 / TPD 3,000,000 / medical 300,000 / TPL 3,000,000"),
]

# --- Boilers & Pressure Vessels (page 58) ---------------------------------
BOILER_RATES = [
    ("material_damage",        0.5, None, "Excess 10% of claim, min Rwf625,000"),
    ("third_party_liability",  0.5, None, "Excess 10% of claim, min Rwf625,000"),
]

# --- Computer & Electronic Equipment All Risks (EEAR) (page 58-59) --------
EEAR_RATES = [
    ("equipment_at_premises",       0.75, None, "Minimum rate; excess 10% min Rwf100,000"),
    ("portable_away_premises",      2.0,  None, "Excess 10% min Rwf100,000"),
    ("unspecified_tender",          1.5,  None, "Where items/values not specified (premises vs away)"),
    ("increased_cost_of_working",   0.75, None, "Data reconstruction; excess 10% min Rwf100,000"),
]

# --- Aviation (page 64) ----------------------------------------------------
AVIATION_RATES = [
    ("hull_all_risks",               0.15,  None, "% of hull value"),
    ("cargo_low",                    0.175, None, "Cargo, low end (nature-dependent)"),
    ("cargo_high",                   0.25,  None, "Cargo, high end (nature-dependent)"),
    ("airport_operators_liability",  0.2,   None, "% of selected limit of indemnity"),
    ("hanger_keeper_liability",      0.2,   None, "Excl professional negligence/defective spare parts"),
    ("pax_liability_per_seat",       0.185, None, "% of indemnity limit per seat; excl non-fare passengers"),
    # crew: normal GPA rates +25% occupational hazard (use pa_gpa with loading)
]

# --- Marine Hull (page 65-66) ---------------------------------------------
MARINE_HULL_RATES = [
    ("hull_all_risks",        0.8,  None, "% of vessel value"),
    ("third_party_liability", 0.25, None, "TPL property: per-event 50m / annual 500m; bodily: per-person 5m / event 25m / annual 200m"),
]
# Per-occupant bodily-injury tiers (flat net premium). (category, amount, note)
MARINE_HULL_OCCUPANT = [
    ("tier_I",    6250, "death 1,000,000 / permanent disablement 1,000,000 / medical 100,000"),
    ("tier_II",   7500, "death 2,000,000 / permanent disablement 2,000,000 / medical 200,000"),
    ("tier_III", 11250, "death 3,000,000 / permanent disablement 3,000,000 / medical 300,000"),
    ("tier_IV",  18000, "death 4,000,000 / permanent disablement 4,000,000 / medical 400,000"),
    ("tier_V",   18750, "death 5,000,000 / permanent disablement 5,000,000 / medical 500,000"),
]

# --- Plate Glass -----------------------------------------------------------
PLATE_GLASS_RATES = [
    ("standard", 2.0, None, "Excess 5% min Rwf100,000"),
]
