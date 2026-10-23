Lightning F.1A Model for FlightGear (www.flightgear.org)
By AJ MacLeod (aj-lists adeptopensource.co uk)

This model is released under the terms of the GPL version 2.

PLEASE: If you can improve any part of this model, do so!  Get in touch with
me or submit your improvements to one of the flightgear email lists.  My
modelling skills are distinctly limited as can be seen, so I have no artistic
pride to swallow :-) 

Requests (in addition to the general one above)

Pilot's Notes - I have the F.6 Notes and FRCs.  Notes for the F.1 or F.1A
would be wonderful...

Better sounds.  Paul's engine startup sounds have been a big improvement,
but any genuine Lightning sound recordings would still be welcomed -
particularly various cockpit warnings etc.  There are still several around
in at least ground running condition so this shouldn't be impossible to get.

Wind Tunnel Data!  Anyone who can lay hands on wind tunnel data for any mark
of Lightning is hereby pleaded with to send me a copy, or better still add
it to the JSBSim FDM config :-) I already have Cl,Cd,Cm vs Alpha for 0 and 
full flap deflection, but need much more data.

If anyone with flying hours on any Lightning mark has any observations on
the in-flight behaviour of this model and how it differs from their memory
of reality, I would be thrilled to hear - I'm not expecting the news to be
good, just want to hear how it can be made better.

Not immediately obvious features:

All production Lightning variants had proportional braking controlled not by
toe brakes, but by the stick mounted brake lever and rudder pedal position.
This has been implemented in this model - if you have rudder pedals (or a 
joystick with a twist axis) then you can steer using the rudder controls and 
braking at the same time, assuming your config uses the controls.applyBrakes 
wrapper.  Maximum braking effort is applied if the rudder controls are centred.

The squadron markings can be very easily modified - look in the Models/Liveries
 subdirectory to see examples.  Each scheme is defined by a simple XML file - 
please feel free to generate new ones and post them either to me or one of the 
mailing lists...

Credits:

Although this is currently nearly all my own work, I have used bits and pieces
from many other FG models as a starting point.  Credit belongs to at least the
following:

Vivian Meazza	- The Hunter was the main inspiration for this model, and
				nearly all the instruments were initially based on their Hunter
				counterparts.  Some of the Nasal functions began life in the 
				Spitfire and Hurricane.
				Vivian added the "chrome animation" effect and tidied up the
				model.

Julien Pierru	- Developed and added the XML and Nasal based squadron markings
				 switching process.

Syd Adams		- The electrical system was modified from the Beaver model,
				and	probably other parts or methods borrowed from some of his
				cockpits.

Paul(youtube user lightning1975) - Permission to use sound clips from his lightning
				startup	videos at youtube.

Thanks to Vivian, Melchior Franz, Andy Ross and others for their
assistance via IRC on various items over a considerable period of time.

