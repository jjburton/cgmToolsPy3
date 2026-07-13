#=========================================================================
# cgmNCloth_presets
# Practical nCloth (+ optional nucleus) profiles for testing / production.
#
# Section keys:
#   'nc'  - nClothShape attributes
#   'n'   - connected nucleus attributes (optional)
#
# Usage (Maya script editor):
#   import cgm.core.lib.nCloth_utils as NCLOTH
#   NCLOTH.profile_load('silk')          # selection = nCloth / mesh / shape
#   NCLOTH.profile_list()
#=========================================================================

# Clean baseline. Other profiles merge onto this when clean=True.
base = {
    'n': {
        'gravity': 9.8,
        # Remapped to scene up at apply time (y-up -> [0,-1,0], z-up -> [0,0,-1]).
        'gravityDirection': [0.0, -1.0, 0.0],
        'airDensity': 1.0,
        'windSpeed': 0.0,
        'windNoise': 0.0,
        'windDirection': [1.0, 0.0, 0.0],
        'timeScale': 1.0,
        # cm scene units (Maya default). Use 1.0 if working in meters.
        'spaceScale': 0.01,
        'subSteps': 6,
        'maxCollisionIterations': 8,
        'usePlane': False,
        'planeFriction': 0.1,
        'planeBounce': 0.0,
        'planeStickiness': 0.0,
    },
    'nc': {
        'isDynamic': True,
        'collide': True,
        'bounce': 0.0,
        'friction': 0.1,
        'stickiness': 0.0,
        'stretchResistance': 40.0,
        'compressionResistance': 20.0,
        'bendResistance': 0.5,
        'bendAngleDropoff': 0.4,
        'shearResistance': 40.0,
        'restitutionAngle': 360.0,
        'restitutionTension': 1000.0,
        'damp': 0.1,
        'drag': 0.05,
        'tangentialDrag': 0.0,
        'lift': 0.05,
        'pointMass': 1.0,
        'pushOut': 0.0,
        'pushOutRadius': 10.0,
        'rigidity': 0.0,
        'deformResistance': 0.0,
        'inputMeshAttract': 0.0,
        'inputAttractDamp': 0.5,
        'restLengthScale': 1.0,
        'pressure': 0.0,
        'pressureDamping': 0.0,
        'ignoreSolverGravity': False,
        'ignoreSolverWind': False,
        'localSpaceOutput': False,
    },
}

# Light flowing fabric (scarves, chiffon, silk shirt hem).
silk = {
    'n': {
        'subSteps': 8,
        'maxCollisionIterations': 10,
    },
    'nc': {
        'pointMass': 0.35,
        'stretchResistance': 60.0,
        'compressionResistance': 10.0,
        'bendResistance': 0.05,
        'bendAngleDropoff': 0.6,
        'shearResistance': 30.0,
        'damp': 0.04,
        'drag': 0.08,
        'lift': 0.1,
        'friction': 0.05,
    },
}

# General mid-weight cloth (tees, curtains, drapes).
cotton = {
    'n': {
        'subSteps': 6,
    },
    'nc': {
        'pointMass': 1.0,
        'stretchResistance': 50.0,
        'compressionResistance': 20.0,
        'bendResistance': 0.4,
        'bendAngleDropoff': 0.4,
        'shearResistance': 40.0,
        'damp': 0.1,
        'drag': 0.05,
        'lift': 0.05,
        'friction': 0.15,
    },
}

# Heavier / stiffer fabric.
denim = {
    'n': {
        'subSteps': 6,
        'maxCollisionIterations': 10,
    },
    'nc': {
        'pointMass': 2.0,
        'stretchResistance': 120.0,
        'compressionResistance': 60.0,
        'bendResistance': 2.5,
        'bendAngleDropoff': 0.3,
        'shearResistance': 80.0,
        'damp': 0.15,
        'drag': 0.04,
        'friction': 0.4,
    },
}

# Form-holding, little flutter.
leather = {
    'n': {
        'subSteps': 5,
    },
    'nc': {
        'pointMass': 2.5,
        'stretchResistance': 180.0,
        'compressionResistance': 100.0,
        'bendResistance': 12.0,
        'bendAngleDropoff': 0.2,
        'shearResistance': 120.0,
        'damp': 0.25,
        'drag': 0.03,
        'friction': 0.5,
        'deformResistance': 0.2,
    },
}

# Flags / banners — catch air, soft bend.
flag = {
    'n': {
        'airDensity': 1.5,
        'subSteps': 8,
        'maxCollisionIterations': 10,
        # Tweak wind in the nucleus after load for your shot.
        'windSpeed': 8.0,
        'windNoise': 2.0,
        'windDirection': [1.0, 0.0, 0.0],
    },
    'nc': {
        'pointMass': 0.5,
        'stretchResistance': 80.0,
        'compressionResistance': 15.0,
        'bendResistance': 0.1,
        'bendAngleDropoff': 0.7,
        'shearResistance': 40.0,
        'damp': 0.05,
        'drag': 0.12,
        'lift': 0.15,
        'friction': 0.05,
    },
}

# Character-safe / less explosive. Good first pass on apparel.
stable = {
    'n': {
        'subSteps': 8,
        'maxCollisionIterations': 12,
        'timeScale': 1.0,
    },
    'nc': {
        'pointMass': 1.0,
        'stretchResistance': 200.0,
        'compressionResistance': 100.0,
        'bendResistance': 1.0,
        'bendAngleDropoff': 0.35,
        'shearResistance': 80.0,
        'damp': 0.2,
        'drag': 0.05,
        'friction': 0.2,
        'pushOut': 0.1,
        'pushOutRadius': 5.0,
        # Mild follow of the animated input (raise if still sliding off).
        'inputMeshAttract': 0.15,
        'inputAttractDamp': 0.6,
    },
}

# Stretchy / bouncy rubber or latex.
rubber = {
    'n': {
        'subSteps': 8,
    },
    'nc': {
        'pointMass': 1.2,
        'stretchResistance': 15.0,
        'compressionResistance': 10.0,
        'bendResistance': 0.8,
        'shearResistance': 20.0,
        'damp': 0.05,
        'bounce': 0.4,
        'friction': 0.6,
        'stickiness': 0.05,
        'drag': 0.04,
    },
}

# Faster scrubbing — fewer collide iters, more damp.
preview = {
    'n': {
        'subSteps': 3,
        'maxCollisionIterations': 4,
    },
    'nc': {
        'stretchResistance': 80.0,
        'compressionResistance': 40.0,
        'bendResistance': 1.0,
        'damp': 0.35,
        'friction': 0.2,
    },
}

# Soft pin / cling to input mesh (hoods, pockets that should track).
inputAttract = {
    'nc': {
        'inputMeshAttract': 1.0,
        'inputAttractDamp': 0.5,
        'stretchResistance': 100.0,
        'bendResistance': 2.0,
        'damp': 0.2,
    },
}

# Zero nucleus wind / plane; reset cloth motion helpers.
calm = {
    'n': {
        'windSpeed': 0.0,
        'windNoise': 0.0,
        'airDensity': 1.0,
        'usePlane': False,
    },
    'nc': {
        'pressure': 0.0,
        'lift': 0.05,
        'drag': 0.05,
        'ignoreSolverWind': False,
        'ignoreSolverGravity': False,
    },
}
