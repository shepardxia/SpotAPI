"""JSON-based session saver using the SaverProtocol interface."""

import json
import os
from typing import Any, List, Mapping

from readerwriterlock import rwlock

from clautify.exceptions import SaverError
from clautify.types.interfaces import SaverProtocol

__all__ = ["JSONSaver", "SaverProtocol"]


class JSONSaver(SaverProtocol):
    """
    CRUD methods for JSON files
    """

    __slots__ = (
        "path",
        "rwlock",
        "rlock",
        "wlock",
    )

    def __init__(self, path: str = "sessions.json") -> None:
        self.path = path

        self.rwlock = rwlock.RWLockFairD()
        self.rlock = self.rwlock.gen_rlock()
        self.wlock = self.rwlock.gen_wlock()

    def __str__(self) -> str:
        return "JSONSaver()"

    def save(self, data: List[Mapping[str, Any]], **kwargs) -> None:
        """
        Save data to a JSON file

        Kwargs
        -------
        overwrite (bool, optional): Defaults to False.
            Overwrites the entire file instead of appending.
        """
        with self.wlock:
            if len(data) == 0:
                raise ValueError("No data to save")

            if not os.path.exists(self.path):
                open(self.path, "w").close()

            if kwargs.get("overwrite", False):
                current = []
            else:
                with open(self.path, "r") as f:
                    file_content = f.read()
                    current = json.loads(file_content) if file_content.strip() else []
                    # Checks if identifier exists
                    if current:
                        current = [
                            item for item in current if not any(item["identifier"] == d["identifier"] for d in data)
                        ]

            current.extend(data)

            with open(self.path, "w") as f:
                json.dump(current, f, indent=4)

    def load(self, query: Mapping[str, Any], **kwargs) -> Mapping[str, Any]:
        """
        Load data from a JSON file given a query

        Kwargs
        -------
        allow_collisions (bool, optional): Defaults to False.
            Raises an error if the query returns more than one result.
        """
        with self.rlock:
            if not query:
                raise ValueError("Query dictionary cannot be empty")

            with open(self.path, "r") as f:
                data = json.load(f)

            allow_collisions = kwargs.get("allow_collisions", False)
            matches: List[Mapping[str, Any]] = []

            for item in data:
                if all(item[key] == query[key] for key in query):
                    matches.append(item)
                    # Save time by checking for collisions each iteration
                    if allow_collisions and len(matches) > 1:
                        raise SaverError("Collision found")

            if len(matches) >= 1:
                return matches[0]

            raise SaverError("Item not found")

    def delete(self, query: Mapping[str, Any], **kwargs) -> None:
        """
        Delete data from a JSON file given a query

        Kwargs
        -------
        all_instances (bool, optional): Defaults to True.
            Deletes all instances of the query.

        clear_all (bool, optional): Defaults to False.
            Deletes all data in the file.
        """
        with self.wlock:
            if not query:
                raise ValueError("Query dictionary cannot be empty")

            delete_all_instances = kwargs.get("all_instances", True)
            clear_all = kwargs.get("clear_all", False)

            if clear_all:
                with open(self.path, "w") as f:
                    return json.dump([], f)

            with open(self.path, "r") as f:
                data = json.load(f)

            assert isinstance(data, list), "JSON must be an array"

            # Copy the list to avoid modifying the original
            for item in data.copy():
                if all(item[key] == query[key] for key in query):
                    data.remove(item)
                    if not delete_all_instances:
                        break

            with open(self.path, "w") as f:
                json.dump(data, f, indent=4)
