## Email address ##
Matches standard email addresses (e.g. user@example.com).

Example matches:
user@example.com
name+tag@domain.co

Pattern:
[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}

## Phone number ##
Matches 10-digit US-style phone numbers with optional separators (dashes, dots, or spaces).

Example matches:
9143094996
914-309-4996
914.309.4996

Pattern:
\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b

## Social Security Number ##
Matches US Social Security numbers in XXX-XX-XXXX format.

Example matches:
123-45-6789

Pattern:
\b\d{3}-\d{2}-\d{4}\b


## Credit card number ##
Matches 16-digit card numbers separated by spaces or dashes (4 groups of 4 digits).

Example matches:
4265 5256 0839 8752
4265-5256-0839-8752

Pattern:
\b(?:\d{4} \d{4} \d{4} \d{4}|\d{4}-\d{4}-\d{4}-\d{4})\b


## IP Address ##
Matches IPv4 addresses in dotted-quad notation.

Example matches:
192.168.0.1
10.0.0.1

Pattern:
\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b


## Address ##
Detects physical addresses, street names, cities, and locations using contextual language analysis rather than pattern matching.

Example matches:
123 Main Street, Springfield
London, United Kingdom
1600 Pennsylvania Avenue NW
Limitations:

If the check times out, the request proceeds (not blocked).
Partial addresses without city/state may be missed
Ambiguous location names (e.g. "Paris" as a name vs city) depend on context
Non-standard or abbreviated formats may not be detected
Enabling this adds latency depending on the size of the request.




