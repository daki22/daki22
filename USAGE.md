# expsearch – pretraga isteklih domena (procena ≥ 5000 €)

Bez zavisnosti (samo Python 3.9+ stdlib).

## Tok rada
1. Izvezi CSV sa ExpiredDomains.net (Export), GoDaddy Auctions, DropCatch, Dynadot…
   Prepoznaju se kolone: `Domain, BL, DP/RD, DR/DA, ABY, WBY, Price, EndDate, Status, Spam`.
2. Pretraži:
   ```
   python3 -m expsearch search lista.csv --min-value 5000 --tld com --tld ai --no-hyphen --no-digits
   python3 -m expsearch search lista.csv --live --csv rezultat.csv   # + RDAP/Wayback provera
   python3 -m expsearch check neki-domen.com --rd 300 --authority 40
   ```
3. Testovi: `python3 -m unittest discover tests`

## Napomena
Vrednost je **heuristička procena** (dužina, TLD, reč/keyword, referring domains,
autoritet, starost, Wayback). Podešava se u `expsearch/valuation.py` (`CONFIG`).
Pre kupovine proveri uporedive prodaje (NameBio), spam/penalty istoriju backlinkova
(Ahrefs/Majestic) i trenutnu dostupnost kod registrara.
