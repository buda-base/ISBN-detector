# ISBN-detector

ISBN detector for BDRC volumes. This repository is meant to be temporary and contain code to detect ISBNs in BDRC volumes.

Example: MW1PD95844 has one ISBN-10 in our database (7800571289), but:
- it is the ISBN-10 for volume 1 only, we need to get the ISBNs for other volumes
- the cover contains the ISBN-13

7,004 ISBN numbers recorded in the database
15,816 potentially needed

Libraries to test:
- https://github.com/ChenjieXu/pyzxing
- https://pypi.org/project/pyzbar/

Complex cases:
- W1KG5875 has 2 different ISBN for hardcover / paperback
- W3CN3406 has the same ISBN for all the volumes
- W23893 has an ISBN for the set and each volume has a different ISBN

Same ISBNs:
- MW29980 / MW29975
- W3CN25679 / W3CN26493