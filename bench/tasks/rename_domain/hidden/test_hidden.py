from models import Account
from svc_1 import account_summary_1
from svc_2 import account_summary_2
from svc_3 import account_summary_3
from svc_4 import account_summary_4
from svc_5 import account_summary_5
from svc_6 import account_summary_6
from svc_7 import account_summary_7
from svc_8 import account_summary_8
from svc_9 import account_summary_9
from svc_10 import account_summary_10
from svc_11 import account_summary_11
from svc_12 import account_summary_12
from svc_13 import account_summary_13


def test_all_renamed():
    a = Account("Zed", 3)
    assert a.account_label() == "Account<Zed>"

def test_h1():
    assert account_summary_1(Account("Zed", 3)) == "Account Zed (tier 4) Account<Zed>"

def test_h2():
    assert account_summary_2(Account("Zed", 3)) == "Account Zed (tier 5) Account<Zed>"

def test_h3():
    assert account_summary_3(Account("Zed", 3)) == "Account Zed (tier 6) Account<Zed>"

def test_h4():
    assert account_summary_4(Account("Zed", 3)) == "Account Zed (tier 7) Account<Zed>"

def test_h5():
    assert account_summary_5(Account("Zed", 3)) == "Account Zed (tier 8) Account<Zed>"

def test_h6():
    assert account_summary_6(Account("Zed", 3)) == "Account Zed (tier 9) Account<Zed>"

def test_h7():
    assert account_summary_7(Account("Zed", 3)) == "Account Zed (tier 10) Account<Zed>"

def test_h8():
    assert account_summary_8(Account("Zed", 3)) == "Account Zed (tier 11) Account<Zed>"

def test_h9():
    assert account_summary_9(Account("Zed", 3)) == "Account Zed (tier 12) Account<Zed>"

def test_h10():
    assert account_summary_10(Account("Zed", 3)) == "Account Zed (tier 13) Account<Zed>"

def test_h11():
    assert account_summary_11(Account("Zed", 3)) == "Account Zed (tier 14) Account<Zed>"

def test_h12():
    assert account_summary_12(Account("Zed", 3)) == "Account Zed (tier 15) Account<Zed>"

def test_h13():
    assert account_summary_13(Account("Zed", 3)) == "Account Zed (tier 16) Account<Zed>"
