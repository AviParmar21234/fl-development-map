from scraper.connectors.primegov import parse_agenda

HTML = """
<table class="item-table-fromdocx" data-id="1" data-sectionid="16524"><tr><td>1. CALL TO ORDER</td></tr></table>
<table class="item-table-fromdocx" data-id="9560" data-itemid="9560"><tr><td>
PB26-0100. 1234 Alton Road - rezoning for a 120-unit multifamily building.
Combine item's attachments into one PDF and view</td></tr></table>
<table class="item-table-fromdocx" data-id="9561" data-itemid="9561"><tr><td>PB26-0101. Variance at 500 Ocean Dr</td></tr></table>
"""


def test_parse_agenda_items_only():
    items = parse_agenda(HTML, "https://x.primegov.com/Portal/Meeting?compiledMeetingDocumentFileId=77")
    assert len(items) == 2  # section header (data-sectionid, no data-itemid) excluded
    link, text = items[0]
    assert link.endswith("compiledMeetingDocumentFileId=77#AgendaItem_9560")
    assert "1234 Alton Road" in text
    assert "Combine item's attachments" not in text
