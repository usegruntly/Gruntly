from slugify import slugify

def test_runs_and_edges():
    assert slugify("  Hello,   World!!  ") == "hello-world"
    assert slugify("a--b__c") == "a-b-c"
    assert slugify("---") == ""
    assert slugify("Python 3.12") == "python-3-12"
