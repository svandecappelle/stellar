- Define

- Universe in 3 parametrable dimentions at install 9:9:9

- resources are: minerals => base resource, , deuterium => combustible, energy => Mw, population => people
    - Each ships / building consume the population
    - There is a max-population on each planet

- All pending actions done by user are stacked into a stack event
    - on each modifications done on the user position is stacked like this:
        - from date of event
        - in order of: defense, attack, research, building, event came from other users

- Implement a planet name generator

- Colonisation could sometime need to add military units on planets with already exists civilisation
  - If civilisation exists and is pacific the population increase after colony established
  - If civilisation is hostile, the planet need to be occupied for several years before autonomous (if not occupied it
    can generate rebellion)