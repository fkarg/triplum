from sqlmodel import Session, SQLModel, create_engine

from triplum.datatype import Collection
from triplum.store.sql.tables import CollectionRow


def test_collection_sql_round_trip():
    collection = Collection(name="Research notes")
    assert collection.id.version == 7

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine, tables=[SQLModel.metadata.tables["collection"]])
    with Session(engine) as session:
        session.add(CollectionRow.model_validate(collection.model_dump()))
        session.commit()

    with Session(engine) as session:
        row = session.get(CollectionRow, collection.id)
        assert row is not None
        assert Collection.model_validate(row, from_attributes=True) == collection
    engine.dispose()
