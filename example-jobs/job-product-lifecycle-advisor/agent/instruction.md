# Product Lifecycle Advisor Job

## Purpose

You are an IT infrastructure planner responsible for tracking and managing product lifecycles across the organization. Use the Red Hat Product Lifecycle Advisor skill ("**SKILL-red-hat-product-lifecycle.md**") to analyze the current infrastructure and create an upgrade roadmap.

## Tasks

1. **For each product/version in the inventory**, use the Product Lifecycle Advisor skill to:

   * Check the current lifecycle phase (Development, Maintenance, End of Life, Extended Support, etc.)
   * Determine end-of-life date
   * Identify what support is available
   * Note any upcoming transitions
2. **Identify risk areas**:

   * Products approaching end-of-life
   * Products in extended support (approaching full end-of-life)
   * Products with known security gaps
   * Unsupported product versions
3. **Create an upgrade roadmap**:

   * Prioritize which systems need immediate upgrades
   * Group by criticality and support risk
   * Suggest upgrade paths and timelines
   * Estimate effort and impact
   * Identify dependencies between systems
4. **Generate compliance and risk reports**:

   * Security risk assessment by product
   * Support coverage gaps
   * Cost implications of staying on current versions
   * Recommendations for each system

## Output Format

Create the following files in the outbox:

1. **lifecycle\_status\_report.md** - Current status of all products with lifecycle phases
2. **upgrade\_roadmap.md** - Detailed roadmap with timelines and priorities
3. **risk\_assessment.json** - JSON with risk scores and impact analysis
4. **compliance\_gaps.md** - Support gaps and security risks
5. **cost\_impact\_analysis.txt** - Business case for upgrades

## Key Information to Include

For each system, provide:

* Product name and current version
* Lifecycle phase
* End of life date
* Recommended upgrade version
* Upgrade priority (Critical, High, Medium, Low)
* Estimated downtime/effort
* Risk of NOT upgrading
* Support SLA implications

