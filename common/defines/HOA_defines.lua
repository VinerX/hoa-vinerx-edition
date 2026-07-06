NDefines.NGame.START_DATE = "581.1.1.12"
NDefines.NGame.END_DATE = "650.1.1.1"
NDefines.NGame.ENERGY_RESOURCE = "wood"
--------------
-- Focus --
--------------
NDefines.NFocus.FOCUS_POINT_DAYS = 1

--------------
-- Graphics --
--------------

NDefines_Graphics.NGraphics.COUNTRY_FLAG_TEX_WIDTH = 82
NDefines_Graphics.NGraphics.COUNTRY_FLAG_TEX_HEIGHT = 129
NDefines.NGraphics.COUNTRY_FLAG_TEX_MAX_SIZE = 2048
NDefines.NGraphics.COUNTRY_FLAG_SMALL_TEX_MAX_SIZE = 512
NDefines.NGraphics.COUNTRY_FLAG_STRIPE_TEX_MAX_WIDTH = 10
NDefines.NGraphics.COUNTRY_FLAG_STRIPE_TEX_MAX_HEIGHT = 8196
NDefines.NGraphics.COUNTRY_FLAG_LARGE_STRIPE_MAX_WIDTH = 41
NDefines.NGraphics.COUNTRY_FLAG_LARGE_STRIPE_MAX_HEIGHT = 24000

-------------------------
-- Misc Default Values --
-------------------------

-- NOTE: These need to stay at 0.5 to make penalties start at 0.5. Please manually set Stability and War Support for nations.
NDefines.NCountry.DEFAULT_STABILITY = 0.5  -- Vanilla is 0.5. Default stability if not scripted otherwise.
NDefines.NCountry.DEFAULT_WAR_SUPPORT = 0.5  -- Vanilla is 0.5. Default war support if not scripted otherwise.
NDefines.NCountry.BASE_STABILITY_PARTY_POPULARITY_FACTOR = 0.05  -- Vanilla is 0.15. A ton of nations start with only one ideology, a very rare occurence in base game
NDefines.NCountry.WAR_SUPPORT_TENSION_IMPACT = 0.2	-- Vanilla is 0.4. Total impact of world tension.
NDefines.NCountry.STARTING_COMMAND_POWER = 10   -- Vanilla is 0. Starting command power for every country
NDefines.NCountry.BASE_MAX_COMMAND_POWER = 200   -- Vanilla is 80. base value for maximum command power
NDefines.NCountry.MAJOR_MIN_FACTORIES = 20  -- Was 30, changed to 20 Vanilla is 35. Need at least these many factories to become a major
NDefines.NCountry.FEMALE_UNIT_LEADER_BASE_CHANCE = {
    0.5, -- country leaders
    0.5, -- army leaders
    0.5, -- navy leaders
    0.5, -- air leaders
    0.5, -- operatives
    0.0, -- scientists ### if its set to 0.5 always runs causes Errors
}

-- Testing AI improvements so Classic Will Work Well
NDefines.NDiplomacy.DIPLOMACY_HOURS_BETWEEN_REQUESTS = 48 --#24 -- How long a country must wait before sending a new diplomatic request.

NDefines.NDiplomacy.VOLUNTEERS_DIVISIONS_REQUIRED = 10  -- Vanilla is 30. This many divisons are required for the country to be able to send volunteers.
NDefines.NDiplomacy.EMBARGO_COST = 50  -- Vanilla is 100. One-time cost
NDefines.NDiplomacy.MAX_TRUST_VALUE = 200  -- Vanilla is 100. Max trust value cap.
NDefines.NDiplomacy.MIN_TRUST_VALUE = -200  -- Vanilla is -100. Min trust value cap.
NDefines.NDiplomacy.MAX_OPINION_VALUE = 150  -- Vanilla is 100. Max opinion value cap.
NDefines.NDiplomacy.MIN_OPINION_VALUE = -150  -- Vanills is -100. Min opinion value cap.
NDefines.NDiplomacy.BASE_IMPROVE_RELATION_SAME_IDEOLOGY_GROUP_MAINTAIN_COST = 0.15  -- Vanilla is 0.2. Political power cost each update when boosting relations with nation of same ideology
NDefines.NDiplomacy.BASE_IMPROVE_RELATION_DIFFERENT_IDEOLOGY_GROUP_MAINTAIN_COST = 0.3  -- Vanilla is 0.4. Political power cost each update when boosting relations with nation of different ideology

NDefines.NTechnology.BASE_YEAR_AHEAD_PENALTY_FACTOR = 1.5  -- Base year ahead penalty. Vanilla is 2
NDefines.NTechnology.BASE_TECH_COST = 80  -- Base cost for a tech. multiplied with tech cost and ahead of time penalties. Vanilla is 100

NDefines.NProduction.BASE_FACTORY_MAX_EFFICIENCY_FACTOR = 40  -- Vanilla is 50. Base max efficiency for factories expressed in %.
NDefines.NProduction.BASE_FACTORY_START_EFFICIENCY_FACTOR = 8  -- Vanilla is 10. Base start efficiency for factories expressed in %

NDefines.NProject.BREAKTHROUGH_DAILY_SCIENTIST_SKILL_GAIN = 15 --- Base Game is 5 (Increased by 2.5 Times)
NDefines.NProject.BREAKTHROUGH_DAILY_TECHNOLOGY_GAIN = 36 --- Base Game is 12 (Increased by 2.5 Times)

NDefines.NBuildings.MAX_SHARED_SLOTS = 25 -- Reduced back to 25 from 30 to remove graphical Bug, Vanilla is 25. Max slots shared by factories

-- DO NOT CHANGE THIS WITHOUT CHANGING THE LOCALIZATION FOR infrastructure_desc. This value is before other modifiers. An additional 5% is granted to all
-- resources from the state INCLUDING resource buildings AND raw resources, which is applied after modifiers. The define below only affects raw resources,
-- hence why 2 separate modifiers are used. @Tran
NDefines.NBuildings.INFRASTRUCTURE_RESOURCE_BONUS = 0.05  -- Vanilla is 0.2. Multiplicative resource bonus for each level of (non damaged) infrastructure

NDefines.NBuildings.SUPPLY_ROUTE_RESOURCE_BONUS = 0.05 -- Vanilla is 0.2 multiplicative resource bonus for having a railway/naval connection to the capital

NDefines.NBuildings.ANTI_AIR_SUPERIORITY_MULT = 6  -- Vanilla is 5. How much air superiority reduction to the enemy does our AA guns? Normally each building level = -1 reduction. With this multiplier.

NDefines.NTrade.DISTANCE_TRADE_FACTOR = -0.12  -- Vanilla is -0.02. Upped from -0.1 Trade factor is modified by distance times this

NDefines.NOperatives.AGENCY_CREATION_FACTORIES = 4  -- Vanilla is 5. Number of factories used to create an intelligence agency
NDefines.NOperatives.MAX_OPERATIVE_SLOT_FROM_AGENCY_UPGRADES = 3	-- Vanilla is 1. -- max operative slots gained from upgrades

NDefines.NResistance.RESISTANCE_TARGET_BASE = 60 -- Vanilla is 35 (Occupation laws are different). Base resistance target percentage
NDefines.NResistance.RESISTANCE_TARGET_MODIFIER_HAS_CLAIM = -10 -- Vanilla is -5. Resistance target modifier in % for states we have claim
NDefines.NResistance.RESISTANCE_TARGET_MODIFIER_OCCUPIED_CAPITULATED = 5 -- Vanilla is 10. Resistance target modifier when the enemy is capitulated
NDefines.NResistance.RESISTANCE_POP_LOW_CUTOFF = 4500  -- Vanilla is 10000. Defines Low Cutoff pop count modifier
NDefines.NResistance.RESISTANCE_POP_VERY_LOW_CUTOFF = 1000  -- Vanilla is 1000. Defines Low Cutoff pop count modifier
NDefines.NResistance.RESISTANCE_TARGET_MODIFIER_POP_LOW = -10.0  -- Vanilla is -20. Resistance modifier low pop
NDefines.NResistance.RESISTANCE_TARGET_MODIFIER_POP_VERY_LOW = -30.0 -- Vanilla is -50. Resistance modifier very low pop

NDefines.NResistance.GARRISON_TEMPLATE_SCORE_IC_FACTOR = 0.9  -- Vanilla is 1.0. AI uses these defines while calculating garrison template score of a template.
NDefines.NResistance.GARRISON_TEMPLATE_SCORE_MANPOWER_FACTOR = 0.1  -- Vanilla is 0.05. Formula is (template_ic * ic_factor + template_manpower * manpower_factor ) / template_supression (lower is better)

NDefines.NResistance.SUPPRESSION_NEEDED_BY_RESISTANCE_POINT = 0.6 -- Vanilla is 0.75. Number of suppression point we need for each 1% of resistance
NDefines.NResistance.SUPPRESSION_NEEDED_LOWER_CAP = 4.0	-- Vanilla is 10.0. If resistance is lower than this value then we always act as though it is at the define for the purpose of suppresion requirements
NDefines.NResistance.SUPPRESSION_NEEDED_UPPER_CAP = 60.0 -- Vanilla is 50.0. If resistance is greater than this value then we always act as though it is at the define for the purpose of suppresion requirements

NDefines.NResistance.RESISTANCE_TARGET_TO_REENABLE_RESISTANCE = 15 -- resistance will be disabled once it reaches zero and will not be reenabled until resistance target reaches above this value

NDefines.NResistance.RESISTANCE_TARGET_MIN_CAP_FOR_NON_COMPLIANCE = 10

-------------------
-- Combat Values --
-------------------

NDefines.NMilitary.RECON_SKILL_IMPACT = 6  -- Vanilla is 5. How many skillpoints is a recon advantage worth when picking a tactic.
NDefines.NMilitary.INITIATIVE_PICK_COUNTER_ADVANTAGE_FACTOR = 0.4  -- Vanilla is 0.35. Advantage per leader level for picking a counter
NDefines.NIntel.RECON_INTEL_BONUS = 0.1  -- Vanilla is 0.075. Each recon gives this bonus to overall gathered land intel in combat

-----------------------------------
-- Tension and Peace Conferences --
-----------------------------------

NDefines.NDiplomacy.MAX_TRUST_VALUE = 150  -- Vanilla is 100. Max trust value cap.
NDefines.NDiplomacy.MIN_TRUST_VALUE = -150  -- Vanilla is 100. Min trust value cap.
NDefines.NDiplomacy.OPINION_FOR_DEMO_FROM_WT_GENERATION = -0.5  -- Vanilla is -2.0. How much less do democracies like us if we generate world tension
NDefines.NDiplomacy.TENSION_SIZE_FACTOR = 0.6  -- Vanilla is 1.0. All action tension values are multiplied by this value
NDefines.NDiplomacy.PEACE_SCORE_SCALE_FACTOR = 1.8  -- Vanilla is 1.35. Losers' total value times this factor becomes the default total peace conference score that is distributed to the winners.
NDefines.NMilitary.WAR_SCORE_LOSSES_RATIO = 4  -- Vanilla is 0.5 (HoA has far less manpower). War score gained for every 1000 casualties
NDefines.NNavy.WAR_SCORE_GAIN_FOR_SUNK_SHIP_MANPOWER_FACTOR = 0.02  -- Vanilla is 0.001 (HoA has far less manpower). War score gained for every manpower killed when sinking a ship

NDefines.NDiplomacy.OPINION_FOR_DEMO_FROM_WT_GENERATION = -1.0	-- Vanilla is -2.0. How much less do democracies like us if we generate world tension
NDefines.NDiplomacy.EMBARGO_THREAT_THRESHOLD = 5  -- Vanilla is 30. Target-generated threat threshold to allow embargo (affected by modifiers)

NDefines.NDiplomacy.TENSION_STATE_VALUE = 1.7  -- Vanilla is 2. Tension value gained by annexing one state

--------------
-- Military --
--------------

NDefines.NMilitary.EXPERIENCE_LOSS_FACTOR = 2.0	-- Scale to smaller unit sizes
NDefines.NMilitary.FIELD_EXPERIENCE_SCALE = 0.06  -- Scale to smaller unit sizes
NDefines.NMilitary.DIVISION_SIZE_FOR_XP = 5  -- Vanilla is 8. How many battalions should a division have to count as a full divisions when calculating XP stuff

NDefines.NMilitary.CORPS_COMMANDER_DIVISIONS_CAP = 16 --24
NDefines.NMilitary.FIELD_MARSHAL_DIVISIONS_CAP = 16 --24
NDefines.NMilitary.FIELD_MARSHAL_ARMIES_CAP = 3 --5

NDefines.NMilitary.BASE_CAPTURE_EQUIPMENT_RATIO = 0.1  -- Vanilla is 0.0. Adding a bit of base equipment capturing makes sense for the universe

NDefines.NMilitary.BASE_FORT_PENALTY = -0.10 -- Nerf defensive bonus, from -0.15

NDefines.NMilitary.SLOWEST_SPEED = 3 -- Vanilla is 4

NDefines.NMilitary.LAND_AIR_COMBAT_MAX_PLANES_PER_ENEMY_WIDTH = 1  -- Vanilla is 3. How many CAS/TAC can enter a combat depending on enemy width there
NDefines.NMilitary.LAND_AIR_COMBAT_STR_DAMAGE_MODIFIER = 0.24   -- Vanilla is 0.032. Air global damage modifier
NDefines.NMilitary.LAND_AIR_COMBAT_ORG_DAMAGE_MODIFIER = 0.24   -- Vanilla is 0.032. Air global damage modifier
NDefines.NMilitary.ENEMY_AIR_SUPERIORITY_IMPACT = -0.15         -- Vanilla is -0.15. effect on defense due to enemy air superiorty
NDefines.NMilitary.ANTI_AIR_TARGETTING_TO_CHANCE = 0.03		-- Vanilla is 0.07. Balancing value to determine the chance of ground AA hitting an attacking airplane, affecting both the effective average damage done by AA to airplanes, and the reduction of damage done by airplanes due to AA support
NDefines.NMilitary.ANTI_AIR_ATTACK_TO_AMOUNT = 0.005  -- Vanilla is 0.005. Balancing value to convert equipment stat anti_air_attack to the random % value of airplanes being hit.
NDefines.NMilitary.ENEMY_AIR_SUPERIORITY_SPEED_IMPACT = -0.2    -- Vanilla is 0.3. Effect on speed due to enemy air superiority
NDefines.NMilitary.AIR_SUPPORT_BASE = 0.2 -- Vanilla is 0.25. CAS bonus factor for air support modifier for land unit in combat


NDefines.NAir.FIELD_EXPERIENCE_SCALE = 0.002  --Vanilla is 0.0004
NDefines.NAir.AIR_WING_COUNTRY_XP_FROM_TRAINING_FACTOR = 0.005	-- Vanilla is 0.003. Factor on country Air XP gained from wing training

NDefines.NProduction.MIN_POSSIBLE_TRAINING_MANPOWER = 2500  -- Vanilla is 100000 (HoA has far less manpower). How many deployment lines minimum can be training
NDefines.NProduction.MAX_EQUIPMENT_RESOURCES_NEED = 4  -- Vanilla is 3. Max number of different strategic resources an equipment can be dependent on

--------------
-- Navy --
--------------
NDefines.NNavy.NAVAL_TRANSFER_BASE_SPEED = 15 -- Vanilla is 6. base speed of units on water being transported
NDefines.NNavy.ANTI_AIR_TARGETTING_TO_CHANCE = 0.2  -- Vanilla is 0.2. Balancing value to convert averaged equipment stats (anti_air_targetting and naval_strike_agility) to probability chances of airplane being hit by navies AA.

--------------
-- AIR --
--------------

NDefines.NAir.ACE_EARN_CHANCE_BASE = 0.02          -- 1% base chance per roll
NDefines.NAir.ACE_EARN_CHANCE_PLANES_MULT = 0.00015 -- +0.0005% chance per plane in the wing (decimal 0.00005)

--------------
-- Politics --
--------------

NDefines.NPolitics.BASE_POLITICAL_POWER_INCREASE = 2.5    -- Weekly increase of PP. -- default 2
NDefines.NPolitics.ARMY_LEADER_COST = 10   -- default 5
NDefines.NPolitics.NAVY_LEADER_COST = 10   -- default 5

------------
-- Supply --
------------
NDefines.NSupply.INFRA_TO_SUPPLY = 0.7  -- 1 Infra will now support 1 20-width without supply support -- Vanilla is 0.3 Each level of infra gives this many supply (1.5)
NDefines.NSupply.VP_TO_SUPPLY_BASE = 0.3  -- Vanilla is 0.2. Bonus to supply from a VP, no matter the level (1)
NDefines.NSupply.SUPPLY_BASE_MULT = 0.3  -- Vanilla is 0.2. Multiplier on supply base values
NDefines.NSupply.SUPPLY_HUB_FULL_MOTORIZATION_TRUCK_COST = 40.0  -- Vanilla is 80. How many trucks does it cost to fully motorize a hub

NDefines.NSupply.RAILWAY_BASE_FLOW = 10.0  -- Vanilla is 10. How much base flow railway gives when a node connected to its capital/a naval node by a railway

NDefines.NSupply.CAPITAL_STARTING_PENALTY_PER_PROVINCE = 0.4  -- Vanilla is 0.5. Starting penalty that will be added as supply moves away from its origin (modified by stuff like terrain)

NDefines.NSupply.AVAILABLE_MANPOWER_STATE_SUPPLY = 7.2 -- SUPPLY FROM STATE POPULATION (TEMP) (Default 0.18 from Vanilla - Setting to 1.0 Calculation is 0.01 Supply per 10,000 Pop)

------------------
-- AI Diplomacy --
------------------

NDefines.NDiplomacy.EMBARGO_SAME_IDEOLOGY_AI_WEIGHT = -75  -- Vanilla is -20. AI weight for same ideology
NDefines.NDiplomacy.EMBARGO_DIFFERENT_IDEOLOGY_AI_WEIGHT = -25  -- Vanilla is 15. AI weight for different ideology

NDefines.NAI.BASE_RELUCTANCE = 30  -- Vanilla is 20. Base reluctance applied to all diplomatic offers
NDefines.NAI.DIPLOMACY_FACTION_SAME_IDEOLOGY_MAJOR = 5  -- Vanilla is 10. AI bonus acceptance when being asked about faction is a major of the same ideology
NDefines.NAI.DIPLOMACY_FACTION_GLOBAL_TENSION_FACTOR = 0.1  -- Vanilla is 0.2. How much the AI takes global tension into account when considering faction actions
NDefines.NAI.DIPLOMACY_FACTION_WAR_RELUCTANCE = -75  -- Vanilla is -50. Penalty to desire to enter a faction with a country that we are not fighting wars together with.
NDefines.NAI.DIPLOMACY_SCARED_MINOR_EXTRA_RELUCTANCE = -100  -- Vanilla is -50. Extra reluctance to join stuff as scared minor

NDefines.NAI.GENERATE_WARGOAL_THREAT_BASELINE = 0.0
NDefines.NAI.DIPLOMACY_SEND_MAX_FACTION = 0.5
NDefines.NAI.FORCE_FACTOR_AGAINST_EXTRA_MINOR = 0.4			-- AI considers generating wargoals against minors below this % of force compared to themselves to get at a bigger enemy.
NDefines.NAI.MAX_EXTRA_WARGOAL_GENERATION = 2				-- AI may want to generate wargoals against weak minors to get at larger enemy, but never more that this at any given time.
NDefines.NAI.WARGOAL_GENERATION_STRENGTH_FACTOR = 1.5	-- Desire to generate wargoal effected negatevely if actor strength is less than this factor of target strength
NDefines.NAI.DECLARE_WAR_RELATIVE_FORCE_FACTOR = 0.4	-- Weight of relative force between nations that consider going to war
NDefines.NAI.DECLARE_WAR_NOT_NEIGHBOR_FACTOR = 0.25		-- Multiplier applied before force factor if country is not neighbor with the one it is considering going to war
NDefines.NAI.DIPLOMACY_ACCEPT_VOLUNTEERS_BASE = 100  -- Vanilla is 50. Base value of volunteer acceptance (help is welcome)
NDefines.NAI.DIPLOMACY_IMPROVE_RELATION_COST_FACTOR = 10.0  -- Vanilla is 5.0. Desire to boost relations subtracts the cost multiplied by this
NDefines.NAI.DIPLO_ACCEPTABLE_DISTANCE_BETWEEN_CAPITALS = 800.0  -- Vanilla is 1000. When scaled distance malus begins to kick in. At double this value, max penalty (above) is achieved

-----------------
-- AI Military --
-----------------

NDefines.NAI.DEPLOY_MIN_EQUIPMENT_PEACE_FACTOR = 0.95  -- Vanilla is 0.98. Required percentage of equipment (1.0 = 100%) for AI to deploy unit in peacetime
NDefines.NAI.DEPLOY_MIN_EQUIPMENT_WAR_FACTOR = 0.90  -- Vanilla is 0.95. Required percentage of equipment (1.0 = 100%) for AI to deploy unit in wartime

NDefines.NAI.PLAN_FACTION_STRONG_TO_EXECUTE = 0.65  -- Vanilla is 0.5. % or more of units in an order to consider executing the plan
NDefines.NAI.PLAN_FACTION_WEAK_TO_ABORT = 0.5  -- Vanilla is 0.65. % or more of units in an order to consider executing the plan
NDefines.NAI.PLAN_ACTIVATION_SUPERIORITY_AGGRO = 1.2  -- Vanilla is 1.0. How aggressive a country is in activating a plan based on how superiour their force is
NDefines.NAI.MIN_PLAN_VALUE_TO_MICRO_INACTIVE = 0.15  -- Vanilla is 0.2. The AI will not consider members of groups which plan is not activated AND evaluates lower than this

NDefines.NAI.AI_FRONT_MOVEMENT_FACTOR_FOR_READY = 0.2  -- Vanilla is 0.25. If less than this fraction of units on a front is moving AI sees it as ready for action

NDefines.NAI.ATTACK_HEAVILY_DEFENDED_LIMIT = 0.8  -- Vanilla is 0.5. AI will not launch attacks against heavily defended fronts unless they consider to have this level of advantage (1.0 = 100%)

NDefines.NAI.ORG_UNIT_STRONG = 0.75  -- Vanilla is 0.75. Organization % for unit to be considered strong
NDefines.NAI.STR_UNIT_STRONG = 0.6  -- Vanilla is 0.75. Strength (equipment) % for unit to be considered strong
NDefines.NAI.ORG_UNIT_WEAK = 0.45  -- Vanilla is 0.15. Organization % for unit to be considered weak
NDefines.NAI.STR_UNIT_WEAK = 0.4  -- Vanilla is 0.2. Strength (equipment) % for unit to be considered weak

NDefines.NAI.HOUR_BAD_COMBAT_REEVALUATE = 60  -- Vanilla is 100. If we are in combat for this amount and it goes shitty then try skipping it.

NDefines.NAI.VP_LEVEL_IMPORTANCE_HIGH = 20  -- Vanilla is 0 seemingly? Victory points with values higher than or equal to this are considered to be of high importance.
NDefines.NAI.VP_LEVEL_IMPORTANCE_MEDIUM = 10  -- Vanilla is 10. Victory points with values higher than or equal to this are considered to be of medium importance.
NDefines.NAI.VP_LEVEL_IMPORTANCE_LOW = 3  -- Vanilla is 0 seemingly? Victory points with values higher than or equal to this are considered to be of low importance.

NDefines.NAI.FIX_SUPPLY_BOTTLENECK_SATURATION_THRESHOLD = 0.25;  -- Try to fix supply bottlenecks if supply node saturation exceeds this value.

--------------
-- AI Other --
--------------

NDefines.NAI.RESEARCH_AHEAD_BONUS_FACTOR = 2.25  -- Vanilla is 2.0. To which extent AI should care about ahead of time bonuses to research
NDefines.NAI.RESEARCH_BONUS_FACTOR = 1.5  -- Vanilla is 0.9. To which extent AI should care about bonuses to research
NDefines.NAI.MIN_FACTORIES_TO_WANT_TO_IMPORT = {  -- minimum number of civilian factories the AI must have to consider importing a resource - per strategic resource. Default 0, array -should- be updated with new resources, or if the order changes.
		0, -- oil
		0, -- mana
		10, -- wood #coal is set to 10
		0, -- gunpowder
		0, -- ores
		0, -- mounts
		0, -- eggs
        0, -- wheat
	}

---------------------
-- Industrial Orgs --
---------------------

NDefines.NAI.INDUSTRIAL_ORG_TRAIT_UNLOCK_RANDOMNESS = 3		-- AI will pick a random from N top traits when choosing a trait to unlock
NDefines.NAI.INDUSTRIAL_ORG_POLICY_CHANGE_RANDOMNESS = 3	-- AI will pick a random from N top policies when choosing a policy to attach to an MIO
NDefines.NAI.INDUSTRIAL_ORG_RESEARCH_ASSIGN_RANDOMNESS = 3	-- AI will pick a random from N top MIOs when choosing an MIO to assign to a research
NDefines.NAI.INDUSTRIAL_ORG_PRODUCTION_ASSIGN_RANDOMNESS = 3-- AI will pick a random from N top MIOs when choosing an MIO to assign to a production line
NDefines.NAI.INDUSTRIAL_ORG_POLICY_CHANGE_SCALE = 1.0		-- Policy change weight will be scaled by this value
NDefines.NAI.INDUSTRIAL_ORG_TRAIT_RANK_FACTOR = 0.80		-- When precomputing weights, traits will affect the final score less the further down the tree they are, by this factor
NDefines.NAI.INDUSTRIAL_ORG_RESEARCH_BONUS_FACTOR = 1.0		-- Research bonus will be multiplied by this factor when evaluating design teams

--- Trying to Reduce AI work Load so we can run Classic well
NDefines.NAI.DAYS_BETWEEN_CHECK_BEST_DOCTRINE = 60       -- #30      -- Recalculate desired best doctrine to unlock with this many days inbetween.
NDefines.NAI.DAYS_BETWEEN_CHECK_BEST_TEMPLATE = 30       -- #14      -- Recalculate desired best template to upgrade with this many days inbetween.
NDefines.NAI.DAYS_BETWEEN_CHECK_BEST_EQUIPMENT = 90      -- #30      -- Recalculate desired best equipment to upgrade with this many days inbetween.
NDefines.NAI.EQUIPMENT_MARKET_UPDATE_FREQUENCY_DAYS = 30 -- #11      -- How often the AI runs its market logic
NDefines.NAI.EQUIPMENT_MARKET_BASE_MARKET_RATIO = 0.5    -- #0.2     -- The AI tries to keep ca this ratio of equipment surplus for sale on the market. Gets modified by equipment_market_for_sale_factor AI strategy.

NDefines.NAI.LAND_DESIGN_CUTOFF_AS_PERCENTAGE_OF_MAX = 0.45

NDefines.NIndustrialOrganisation.ASSIGN_DESIGN_TEAM_PP_COST_PER_DAY = 0.1	                -- Cost in Political Power daily generation when one MIO is assigned to a research slot. If 0, cost is entirely disabled.
NDefines.NIndustrialOrganisation.ASSIGN_INDUSTRIAL_MANUFACTURER_PP_COST_PER_DAY = 0.0		-- Cost in Political Power daily generation when one MIO is assigned to a production line. If 0, cost is entirely disabled.
NDefines.NIndustrialOrganisation.FUNDS_FOR_SIZE_UP = 500					                -- Base Game 700  -- Funds needed for a MIO to increment its size and get points to unlock traits
NDefines.NIndustrialOrganisation.FUNDS_FOR_SIZE_UP_LEVEL_FACTOR = 75		                -- Base Game 100  -- How much each level mutliplies the funds for size up 
NDefines.NIndustrialOrganisation.FUNDS_FOR_SIZE_UP_LEVEL_POW = 1.6   		                -- Base Game 1.8  -- the power we applie to the mio size when calculating funds to level up.
NDefines.NIndustrialOrganisation.UNLOCKED_TRAITS_PER_SIZE_UP = 1			                -- Number of points for unlocking traits obtained when the MIO increments its size
NDefines.NIndustrialOrganisation.DESIGN_TEAM_CHANGE_XP_COST = 0				                -- Base 5 Flat cost added to the XP cost of a new equipment design. If 0, cost is entirely disabled.
NDefines.NIndustrialOrganisation.FUNDS_FOR_RESEARCH_COMPLETION_PER_RESEARCH_COST = 350      --- BASE 500-- Funds added to MIO when the Design Team has completed a research, multiplied by research_cost in technology template
NDefines.NIndustrialOrganisation.FUNDS_FOR_CREATING_EQUIPMENT_VARIANT = 0		            -- Funds added to MIO when a new variant is created with the Design Team assigned to it
NDefines.NIndustrialOrganisation.FUNDS_FROM_MANUFACTURER_PER_IC_PER_DAY = 0.25	            --- #0.25 -- Base Game 0.1 -- Funds added to MIO when a manufacturer is attached to a production line. Added every day proportional to IC produced.
NDefines.NIndustrialOrganisation.MAX_FUNDS_FROM_MANUFACTURER_PER_DAY = 0		            -- Base Game 100 -- Max funds generated per manufacturer per day. Set to 0 for no Maximum.
NDefines.NIndustrialOrganisation.DESIGN_TEAM_RESEARCH_BONUS = 0.05				            -- Research bonus for applying a Design Team that matches the technology
NDefines.NIndustrialOrganisation.ENABLE_TASK_CAPACITY = false					            -- Enable limited task capacity for MIOs
NDefines.NIndustrialOrganisation.DEFAULT_INITIAL_TASK_CAPACITY = 0				            -- Default start task capacity for each MIO (may be overriden in DB)
NDefines.NIndustrialOrganisation.DEFAULT_INITIAL_POLICY_ATTACH_COST = 25		            -- Default start attach cost in PP for policies
NDefines.NIndustrialOrganisation.DEFAULT_INITIAL_ATTACH_POLICY_COOLDOWN = 180	            -- Default start cooldown in days after attaching a policy
NDefines.NIndustrialOrganisation.LEGACY_COST_FACTOR_SCALE = 1.0					            -- Multiplier to use when legacy Designer cost factors is applied to MIOs (<IdeaGroup>_cost_factor)