import pytest


def test_user_settings_attr(django_user_model):
    """
    All user_settings are added on create_user.
    :return:
    """
    username = "user1"
    password = "verystrongpasswordindeed"
    user1 = django_user_model.objects.create_user(username=username, password=password)
    assert hasattr(user1, "user_settings")
    attr_list = [
        "token",
        "created",
    ]
    notif_list = [
        "created",
        "published",
        "returned",
        "event",
    ]
    for attr in attr_list:
        assert hasattr(user1.user_settings, attr)
    for attr in notif_list:
        assert attr in user1.user_settings.settings["UserSettings"]["notifs"]


@pytest.mark.django_db
def test_conform_highstate(minion, highstate):
    highstate = highstate()
    assert minion.conformity()
    assert highstate.success_bool()


@pytest.mark.django_db
def test_not_present_highstate(minion):
    assert minion.conformity() is None


@pytest.mark.django_db
def test_a_dry_run_alone_gives_no_verdict(minion, highstate_diff):
    # highstate_diff is a test=True run with a state reporting None. In test
    # mode that is what Salt reports for anything it cannot predict, so it is
    # not evidence of drift; only real runs are judged. A failing real run is
    # covered in test_conformity.py.
    assert minion.conformity() is None


@pytest.mark.django_db
def test_a_dry_run_that_failed_to_compile_gives_no_verdict(minion, highstate_failed):
    # Also a test=True run. The compile error will be in the next real run,
    # which is what gets judged.
    assert minion.conformity() is None


@pytest.mark.django_db
def test_custom_conformity_false(minion_master):
    assert minion_master.custom_conformity("cmd.run", "alcali --version") == False


@pytest.mark.django_db
def test_custom_conformity(minion_master, alcali_version_state, version_conformity):
    assert minion_master.custom_conformity("cmd.run", "alcali --version") == "2019.2.2"


@pytest.mark.django_db
def test_salt_return_job_args(jobs_arguments):
    assert jobs_arguments.arguments() == "foo 1"
    assert jobs_arguments.keyword_arguments() == "bar=baz"
