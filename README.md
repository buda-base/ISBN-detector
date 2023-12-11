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

W3CN5472

cats:
1) :rePublicationOf (ex: MW1AC8 -> MW2KG209029)
2) MW1GS88140 (images) = MW1KG14712 (no images)
3) error in isbn: MW1KG4294 should be  9789937900461, not 9789937818803
4) same isbn for two unrelated books: W1KG21275 / W665
5) not correctly input in the db: MW8CZ135 has "2140 72030", should be 9787214072030

Cases:
- multi volumes where every volume has a detected isbn (done)
- multi volumes with only only one isbn detected in one or multiple volumes
- multi volumes with different isbns recorded in the db (with question marks)

W8LS25039 has an EAN but no ISBN