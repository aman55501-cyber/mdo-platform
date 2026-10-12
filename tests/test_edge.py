import mdo_edge as e


def test_edge_rule_mine_or_plant_within_150():
    near = e.classify("transportation of coal from ocpl manoharpur mines to ntpc kudgi", "National Thermal Power Corporation Limited", "Chhattisgarh", "Raipur")
    assert near["edge"] == "Yes" and near["mine_km"] <= 150
    far = e.classify("coal transport from ukni deep mines of wcl to ntpc kudgi", "National Thermal Power Corporation Limited", "Chhattisgarh", "Raipur")
    assert far["edge"] == "No"
    korba = e.classify("loading and transportation of coal", "South Eastern Coalfields Limited", "Chhattisgarh", "Korba")
    assert korba["edge"] == "Yes" and "tender city" in korba["mine"]
    talcher = e.classify("loading and transportation", "Mahanadi Coalfields Limited", "Orissa", "Angul")
    assert talcher["edge"] == "No"
    assert e.classify("supply of coal", "Some Plant", "", "")["edge"] == "Unknown"
