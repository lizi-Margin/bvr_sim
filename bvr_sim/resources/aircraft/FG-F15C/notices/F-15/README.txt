Realistic windtunnel based aerodynamic model of an F-15 (C,D) version. See http://zaretto.com/f-15

Models an F-15 with F-100 engines.

Low speed clean should be exactly as an F-15 

The aerodata used is from AFWAL-TR-80-3141, Part I and III. See http://zaretto.com/content/f-14-aerodynamic-data-sources

Richard Harrison rjh@zaretto.com
July 2015

Overview of the model

* F-15C and F-15D variants, including aerodynamic effects.
* Realistic FDM based on windtunnel derived aerodynamic data
* Photorealistic 3d Cockpit with real cockpit textures provided by GeneB from his unique F-15C 80-0007
* Operational weapons and radar
* Full range of sound simulation (buffet, gear, engines, etc..)
* Radar, HUD, VSD, TEWS, MPCD - using Canvas
* Refuelling, stores
* In cockpit engine start (including JFS Startup
* Hydraulics system model
* Electrics system model
* Afterburner flames (with luminosity variance depending on scene brightness)
* External and internal Rembrandt compatible lighting
* ECS pressurisation system model
* Control actuator system model
* Rembrandt ready.
* Tone and voice aural warnings 

V1.2E

Sounds; 
 - Calculation of volumes now in Nasal module, this allows the canopy to have a gradual effect
 - New sounds for GPU
 - Added pilot helment sound proofing to ground services dialog
 - Removed separate external / internal sounds because not needed with new internal volume level calculations
 - Fixed orientation, reference dist, angles and factors for engines, speed brake

Canopy opening now JSBSim model. Opening the canopy will result in loss of cabin pressure.

Added support for walker. This required remapping of certain keys.
   Autothrottle a becomes CTRL-s
   Cycle refuelling switch is now u
   Weapon mode (w) becomes (m)

Added sym switch to HUD, if in symbol reject mode then only show the active target.

Better engine smoke / wing tip contrails

FDM
 - adjusted static friction to better hold with full augmentation on dry surface

Better wing root anti-collision lights
Added Correct stall warning audio tones and vocal warnings for OWS, Caution and fuel.
Canvas optimisations for low frame rates
Fix weapon selection after load when master arm selected.
Improved view positioning for front & backseat.
Rework of lighting, fix halos, rembrandt light points; added lighting dialog to GUI.
Reinstate comm radio support
Overload Warning System (OWS) limits added
Pitch/Roll ratio improvements, takes into account CG% MAC.
Nose Wheel Steering (two modes; normal and maneuvering )

New livery for 144FW 84-0014 (Missouri) and Lakenheath

Added cold and dark to menu (to complement quickstart)

Use of the refuelling switch on ground (opening the hatch) will make a refuelling tanker appear and cause fuel to be added.