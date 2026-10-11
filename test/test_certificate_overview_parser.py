import pytest

from rer_client.parsing import _parse_certificates_overview


@pytest.mark.parametrize(
    ("heading", "expected_cert_type"),
    [("ROCs issued", "ROC"), ("REGOs issued", "REGO")],
)
def test_certificate_overview_derives_type_from_heading(heading, expected_cert_type):
    html = f"""
    <div class="govuk-grid-row">
        <div class="ofgem-rer-stat__item">
            <strong class="ofgem-rer-stat__figure">
                <h2>{heading}</h2>
                12
            </strong>
        </div>
        <div>
            <table>
                <tbody>
                    <tr><td>2026/2027 period</td><td>12</td></tr>
                </tbody>
            </table>
            <dl><dt>REGO balance</dt><dd>12</dd></dl>
            <a class="ofgem-rer-certificate-dashboard-summary__link" href="/breakdown"></a>
            <a class="ofgem-rer-certificate-dashboard-summary__link" href="/history"></a>
        </div>
    </div>
    """

    result = _parse_certificates_overview(html, "GEN0000000")

    assert result.summaries[0].cert_type == expected_cert_type
    assert result.summaries[0].balance == 12


def test_certificate_overview_rejects_unknown_heading():
    html = """
    <div class="govuk-grid-row">
        <div class="ofgem-rer-stat__item">
            <strong class="ofgem-rer-stat__figure">
                <h2>Unknown certificates issued</h2>
                12
            </strong>
        </div>
    </div>
    """

    error = pytest.raises(
        ValueError,
        _parse_certificates_overview,
        html,
        "GEN0000000",
    )

    assert "Unrecognized certificate type heading" in str(error.value)
