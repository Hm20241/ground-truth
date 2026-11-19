"""Flag state from an AIS MMSI (ITU Maritime Identification Digits). v1.0, 2026-11-19 (Ground Truth 0.9.0).

A ship station's MMSI is nine digits, MIDXXXXXX, and its first three digits (the MID, 201-775) name the
administration that issued it. flag_of() turns an MMSI (int or str) into (ISO 3166-1 alpha-2, name) with one
dict lookup, so the ship feed can label ~2,000 ships every 5 minutes for free. Territories with their own MID
keep their own code (477 HK, 453 MO, 236 GI, 231 FO, 331 GL, 358 PR, ...); the Azores (204) and Madeira (255)
are PT, and the French southern islands are TF.

None means "no flag from this number": coast stations (00MID...), group calls (0MID...), SAR aircraft
(111MID...), handheld VHF (8MID...), craft tied to a parent ship (98MID...), aids to navigation (99MID...),
SART/MOB/EPIRB (970.., 972.., 974..), anything not nine ASCII digits, and MIDs the ITU has not allocated.

Source: the ITU MARS "Table of Maritime Identification Digits" (itu.int/gladapp/Allocation/MIDs, the table
behind itu.int/en/ITU-R/terrestrial/fmd/Pages/mid.aspx), read 2026-11-19, cross-checked against the Wikipedia
article "Maritime identification digits" (revision of 2026-11-14): the same 292 MIDs. 306 is shared by Curacao,
Sint Maarten and Bonaire/Sint Eustatius/Saba; it maps to CW. 501 (Adelie Land) maps to TF, as Wikipedia does.

The MID is the flag a ship *declares*, not proof of registry: shadow-fleet tankers often carry false or
fraudulent flags (an MMSI from a registry that never listed them, or one reused after a flag-hop), so treat it
as a hint to check, not a fact.
"""

# MIDs (comma list or a-b range), ISO2, name. One line per row of the ITU table, in its order.
_TABLE = """
201 AL Albania
202 AD Andorra
203 AT Austria
204 PT Portugal (Azores)
205 BE Belgium
206 BY Belarus
207 BG Bulgaria
208 VA Vatican City
209,210 CY Cyprus
211 DE Germany
212 CY Cyprus
213 GE Georgia
214 MD Moldova
215 MT Malta
216 AM Armenia
218 DE Germany
219,220 DK Denmark
224,225 ES Spain
226-228 FR France
229 MT Malta
230 FI Finland
231 FO Faroe Islands
232-235 GB United Kingdom
236 GI Gibraltar
237 GR Greece
238 HR Croatia
239-241 GR Greece
242 MA Morocco
243 HU Hungary
244-246 NL Netherlands
247 IT Italy
248,249 MT Malta
250 IE Ireland
251 IS Iceland
252 LI Liechtenstein
253 LU Luxembourg
254 MC Monaco
255 PT Portugal (Madeira)
256 MT Malta
257-259 NO Norway
261 PL Poland
262 ME Montenegro
263 PT Portugal
264 RO Romania
265,266 SE Sweden
267 SK Slovakia
268 SM San Marino
269 CH Switzerland
270 CZ Czechia
271 TR Turkiye
272 UA Ukraine
273 RU Russia
274 MK North Macedonia
275 LV Latvia
276 EE Estonia
277 LT Lithuania
278 SI Slovenia
279 RS Serbia
301 AI Anguilla
303 US United States (Alaska)
304,305 AG Antigua and Barbuda
306 CW Curacao, Sint Maarten, Caribbean Netherlands
307 AW Aruba
308,309 BS Bahamas
310 BM Bermuda
311 BS Bahamas
312 BZ Belize
314 BB Barbados
316 CA Canada
319 KY Cayman Islands
321 CR Costa Rica
323 CU Cuba
325 DM Dominica
327 DO Dominican Republic
329 GP Guadeloupe
330 GD Grenada
331 GL Greenland
332 GT Guatemala
334 HN Honduras
336 HT Haiti
338 US United States
339 JM Jamaica
341 KN Saint Kitts and Nevis
343 LC Saint Lucia
345 MX Mexico
347 MQ Martinique
348 MS Montserrat
350 NI Nicaragua
351-357 PA Panama
358 PR Puerto Rico
359 SV El Salvador
361 PM Saint Pierre and Miquelon
362 TT Trinidad and Tobago
364 TC Turks and Caicos Islands
366-369 US United States
370-374 PA Panama
375-377 VC Saint Vincent and the Grenadines
378 VG British Virgin Islands
379 VI US Virgin Islands
401 AF Afghanistan
403 SA Saudi Arabia
405 BD Bangladesh
408 BH Bahrain
410 BT Bhutan
412-414 CN China
416 TW Taiwan
417 LK Sri Lanka
419 IN India
422 IR Iran
423 AZ Azerbaijan
425 IQ Iraq
428 IL Israel
431,432 JP Japan
434 TM Turkmenistan
436 KZ Kazakhstan
437 UZ Uzbekistan
438 JO Jordan
440,441 KR South Korea
443 PS Palestine
445 KP North Korea
447 KW Kuwait
450 LB Lebanon
451 KG Kyrgyzstan
453 MO Macao
455 MV Maldives
457 MN Mongolia
459 NP Nepal
461 OM Oman
463 PK Pakistan
466 QA Qatar
468 SY Syria
470,471 AE United Arab Emirates
472 TJ Tajikistan
473,475 YE Yemen
477 HK Hong Kong
478 BA Bosnia and Herzegovina
501 TF Adelie Land (French Southern Territories)
503 AU Australia
506 MM Myanmar
508 BN Brunei
510 FM Micronesia
511 PW Palau
512 NZ New Zealand
514,515 KH Cambodia
516 CX Christmas Island
518 CK Cook Islands
520 FJ Fiji
523 CC Cocos (Keeling) Islands
525 ID Indonesia
529 KI Kiribati
531 LA Laos
533 MY Malaysia
536 MP Northern Mariana Islands
538 MH Marshall Islands
540 NC New Caledonia
542 NU Niue
544 NR Nauru
546 PF French Polynesia
548 PH Philippines
550 TL Timor-Leste
553 PG Papua New Guinea
555 PN Pitcairn Islands
557 SB Solomon Islands
559 AS American Samoa
561 WS Samoa
563-566 SG Singapore
567 TH Thailand
570 TO Tonga
572 TV Tuvalu
574 VN Vietnam
576,577 VU Vanuatu
578 WF Wallis and Futuna
601 ZA South Africa
603 AO Angola
605 DZ Algeria
607 TF Saint Paul and Amsterdam Islands
608 SH Ascension Island
609 BI Burundi
610 BJ Benin
611 BW Botswana
612 CF Central African Republic
613 CM Cameroon
615 CG Congo
616 KM Comoros
617 CV Cabo Verde
618 TF Crozet Islands
619 CI Cote d'Ivoire
620 KM Comoros
621 DJ Djibouti
622 EG Egypt
624 ET Ethiopia
625 ER Eritrea
626 GA Gabon
627 GH Ghana
629 GM Gambia
630 GW Guinea-Bissau
631 GQ Equatorial Guinea
632 GN Guinea
633 BF Burkina Faso
634 KE Kenya
635 TF Kerguelen Islands
636,637 LR Liberia
638 SS South Sudan
642 LY Libya
644 LS Lesotho
645 MU Mauritius
647 MG Madagascar
649 ML Mali
650 MZ Mozambique
654 MR Mauritania
655 MW Malawi
656 NE Niger
657 NG Nigeria
659 NA Namibia
660 RE Reunion
661 RW Rwanda
662 SD Sudan
663 SN Senegal
664 SC Seychelles
665 SH Saint Helena
666 SO Somalia
667 SL Sierra Leone
668 ST Sao Tome and Principe
669 SZ Eswatini
670 TD Chad
671 TG Togo
672 TN Tunisia
674 TZ Tanzania
675 UG Uganda
676 CD DR Congo
677 TZ Tanzania
678 ZM Zambia
679 ZW Zimbabwe
701 AR Argentina
710 BR Brazil
720 BO Bolivia
725 CL Chile
730 CO Colombia
735 EC Ecuador
740 FK Falkland Islands
745 GF French Guiana
750 GY Guyana
755 PY Paraguay
760 PE Peru
765 SR Suriname
770 UY Uruguay
775 VE Venezuela
"""


def _parse(table):
    out = {}
    for line in table.strip().splitlines():
        mids, iso2, name = line.split(" ", 2)
        for part in mids.split(","):
            lo, _, hi = part.partition("-")
            for m in range(int(lo), int(hi or lo) + 1):
                out[m] = (iso2, name)
    return out


MID = _parse(_TABLE)  # {int MID: ("ISO2", "name")}
_SHIP_FIRST = frozenset("234567")


def flag_of(mmsi):
    """(iso2, name) for a ship-station MMSI (int or str), else None. Never raises."""
    if isinstance(mmsi, str):
        s = mmsi.strip()
    elif isinstance(mmsi, int) and not isinstance(mmsi, bool):
        s = str(mmsi)  # an int has lost any leading zeros, so 00MID / 0MID numbers fail the length test
    else:
        return None
    if len(s) != 9 or s[0] not in _SHIP_FIRST or not (s.isdigit() and s.isascii()):
        return None
    return MID.get(int(s[:3]))


def iso2_of(mmsi):
    """ISO2 flag code for a ship-station MMSI, or "" (for compact feed rows)."""
    f = flag_of(mmsi)
    return f[0] if f else ""
