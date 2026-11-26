import json

from ..core.source import Source, SourceInfo

DATE = "20260927"
URL = f"https://ogd-static.voteinfo-app.ch/v1/ogd/sd-t-17-02-{DATE}-eidgAbstimmung.json"
FILE = f"{DATE}.json"


class FederalVotes(Source):
    info = SourceInfo(
        id="federal_votes",
        title="Federal popular votes, results per commune",
        publisher="Federal Statistical Office (FSO / BFS)",
        homepage="https://opendata.swiss/en/dataset/echtzeitdaten-am-abstimmungstag-zu-eidgenoessischen-abstimmungsvorlagen",
        license="Open use, source must be named (Source: FSO)",
        description=f"Final results of the federal votes of {DATE[6:]}.{DATE[4:6]}.{DATE[:4]} for every commune: yes share "
        "and turnout. Postal-vote-only counting districts are folded into their commune by BFS.",
        used_for=["Vote lenses"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force)

    def process(self):
        d = json.loads((self.raw_dir / FILE).read_text(encoding="utf-8"))
        ballots = []
        for v in d["schweiz"]["vorlagen"]:
            title = {t["langKey"]: t["text"] for t in v["vorlagenTitel"]}
            communes = {}
            for k in v["kantone"]:
                for g in k["gemeinden"]:
                    r = g["resultat"]
                    if r.get("gebietAusgezaehlt"):
                        communes[g["geoLevelnummer"]] = [r.get("jaStimmenInProzent"), r.get("stimmbeteiligungInProzent"),
                                                         r.get("anzahlStimmberechtigte")]
            ballots.append({"id": v["vorlagenId"], "title": title, "accepted": v.get("vorlageAngenommen"),
                            "yes": v["resultat"]["jaStimmenInProzent"], "turnout": v["resultat"]["stimmbeteiligungInProzent"],
                            "communes": communes})
        return {"vintage": f"Federal votes of {d['abstimmtag']}", "_files": [FILE], "date": d["abstimmtag"], "ballots": ballots}
