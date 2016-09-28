#!/usr/bin/env python

from pytest import mark, raises
from tests.utils import bdb_transaction_test, poll_result


def test_plugin_type_is_bigchaindb(plugin):
    assert plugin.type == 'BigchainDB'


def test_init_connects_to_driver(plugin):
    from bigchaindb_driver import BigchainDB
    assert isinstance(plugin.driver, BigchainDB)


def test_generate_user(plugin):
    user = plugin.generate_user()
    assert isinstance(user['verifying_key'], str)
    assert isinstance(user['signing_key'], str)


@mark.parametrize('model_name', [
    'manifestation_model_jsonld',
    'manifestation_model_json'
])
def test_save_model(plugin, bdb_driver, model_name, alice_keypair, request):
    model_data = request.getfixturevalue(model_name)
    tx_id = plugin.save(model_data, user=alice_keypair)

    # Poll BigchainDB for the result
    tx = poll_result(
        lambda: bdb_driver.transactions.retrieve(tx_id),
        bdb_transaction_test
    )

    tx_payload = tx['transaction']['data']['payload']
    tx_new_owners = tx['transaction']['conditions'][0]['owners_after']
    assert tx['id'] == tx_id
    assert tx_payload == model_data
    assert tx_new_owners[0] == alice_keypair['verifying_key']


def test_save_raises_on_error(monkeypatch, plugin, manifestation_model_json,
                              alice_keypair):
    from bigchaindb_driver.exceptions import DriverException
    from coalaip.exceptions import EntityCreationError

    def mock_driver_error(*args, **kwargs):
        raise DriverException()
    monkeypatch.setattr(plugin.driver.transactions, 'create',
                        mock_driver_error)

    with raises(EntityCreationError):
        plugin.save(manifestation_model_json, user=alice_keypair)


def test_get_persisted_model_status(plugin, bdb_driver,
                                    persisted_manifestation):
    tx_id = persisted_manifestation['id']

    # Poll BigchainDB for the initial status
    poll_result(
        lambda: plugin.get_status(tx_id),
        lambda result: result['status'] in (
            'valid', 'invalid', 'undecided', 'backlog')
    )

    # Poll BigchainDB until the transaction validates; will fail test if the
    # transaction's status doesn't become valid by the end of the timeout
    # period.
    poll_result(
        lambda: plugin.get_status(tx_id),
        lambda result: result['status'] == 'valid'
    )


def test_nonfound_entity_raises_on_status(monkeypatch, plugin,
                                          persisted_manifestation):
    from bigchaindb_driver.exceptions import NotFoundError
    from coalaip.exceptions import EntityNotFoundError

    def mock_driver_not_found_error(*args, **kwargs):
        raise NotFoundError()
    monkeypatch.setattr(plugin.driver.transactions, 'status',
                        mock_driver_not_found_error)

    with raises(EntityNotFoundError):
        plugin.get_status(persisted_manifestation['id'])


@mark.skip(reason='transfer() not implemented yet')
@mark.parametrize('model_name', [
    'rights_assignment_model_jsonld',
    'rights_assignment_model_json'
])
def test_transfer(plugin, bdb_driver, persisted_manifestation, model_name,
                  alice_keypair, bob_keypair, request):
    model_data = request.getfixturevalue(model_name)
    tx_id = persisted_manifestation['id']

    transfer_tx_id = plugin.transfer(tx_id, model_data,
                                     from_user=alice_keypair,
                                     to_user=bob_keypair)

    # Poll BigchainDB for the result
    transfer_tx = poll_result(
        lambda: bdb_driver.transactions.retrieve(transfer_tx_id),
        bdb_transaction_test
    )

    transfer_tx_fulfillments = transfer_tx['transaction']['fulfillments']
    transfer_tx_conditions = transfer_tx['transaction']['conditions']
    transfer_tx_prev_owners = transfer_tx_fulfillments[0]['owners_before']
    transfer_tx_new_owners = transfer_tx_conditions[0]['owners_after']
    assert transfer_tx['id'] == tx_id
    assert transfer_tx_prev_owners[0] == alice_keypair['verifying_key']
    assert transfer_tx_new_owners[0] == bob_keypair['verifying_key']
