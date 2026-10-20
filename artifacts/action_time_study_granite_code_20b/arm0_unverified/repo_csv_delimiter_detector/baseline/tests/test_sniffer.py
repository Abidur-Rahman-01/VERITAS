from datautils.sniffer import detect_delimiter

def test_comma_delimited():
    sample = "name,age,city\nAlice,30,NY\nBob,25,LA"
    assert detect_delimiter(sample) == ","

def test_semicolon_with_quoted_commas():
    # Many commas appear inside quotes; real delimiter is semicolon
    sample = 'id;tags;amount\n1;"alpha,beta,gamma,delta,epsilon";100\n2;"zeta,eta,theta,iota";200'
    assert detect_delimiter(sample) == ";"

def test_tab_delimited():
    sample = "col1\tcol2\tcol3\nval1\tval2\tval3"
    assert detect_delimiter(sample) == "\t"
