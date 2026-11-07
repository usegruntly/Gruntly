from pager import paginate

def test_other_pages():
    data = list(range(10))
    assert paginate(data, 2, 3) == [3, 4, 5]
    assert paginate(data, 4, 3) == [9]
    assert paginate(data, 5, 3) == []
