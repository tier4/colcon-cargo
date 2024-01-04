# Copyright 2018 Easymov Robotics
# Licensed under the Apache License, Version 2.0

import json
import subprocess

import toml
from colcon_core.logging import colcon_logger
from colcon_core.package_identification import \
    PackageIdentificationExtensionPoint
from colcon_core.plugin_system import satisfies_version

logger = colcon_logger.getChild(__name__)


class CargoPackageIdentification(PackageIdentificationExtensionPoint):
    """Identify Cargo packages with `Cargo.toml` files."""

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(
            PackageIdentificationExtensionPoint.EXTENSION_POINT_VERSION,
            '^1.0')

    def identify(self, metadata):  # noqa: D102
        if metadata.type is not None and metadata.type != 'cargo':
            return

        cargo_toml = metadata.path / 'Cargo.toml'
        if not cargo_toml.is_file():
            return

        data = extract_data(cargo_toml)
        if not data:
            raise RuntimeError(
                'Failed to extract Rust package information from "%s"'
                % cargo_toml.absolute())

        if 'workspaces' in data:
            return

        if not is_binary_crate(cargo_toml):
            return

        if metadata.path != metadata.path.parent:
            parent_cargo = metadata.path.parent / 'Cargo.toml'
            if not parent_cargo.is_file():
                return
            parent_data = extract_data(parent_cargo)

            if not parent_data is None:
                if 'workspaces' in parent_data:
                    if not metadata.path.name in parent_data['workspaces']:
                        return
                else:
                    return

        metadata.type = 'cargo'
        if metadata.name is None:
            metadata.name = data['name']
        metadata.dependencies['build'] |= data['depends']
        metadata.dependencies['run'] |= data['depends']


def extract_data(cargo_toml):
    """
    Extract the project name and dependencies from a Cargo.toml file.

    :param Path corgo_toml: The path of the Cargo.toml file
    :rtype: dict
    """
    content = {}
    try:
        content = toml.load(str(cargo_toml))
    except toml.TomlDecodeError:
        logger.error('Decoding error when processing "%s"'
                     % cargo_toml.absolute())
        return

    workspaces = extract_workspaces(content, cargo_toml)
    data = {}
    if workspaces == None:
        # set the project name - fall back to use the directory name
        toml_name_attr = extract_project_name(content)
        data['name'] = toml_name_attr if toml_name_attr is not None else \
            cargo_toml.parent.name

        depends = extract_dependencies(content)
        # exclude self references
        data['depends'] = set(depends) - {data['name']}
    else:
        data['workspaces'] = workspaces

    return data


def is_binary_crate(cargo_toml):
    """
    Check if a crate is a binary crate or not


    :param Path cargo_toml: The Cargo.toml
    :returns: True if crate kind is binary, False otherwise
    :rtype: [bool]
    """
    cmd = ["cargo", "read-manifest", "--manifest-path", str(cargo_toml)]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode == 0:
        d = json.loads(result.stdout)
        for target in d["targets"]:
            if target["kind"] == "bin":
                return True
    else:
        print(f"WARNING: {result.stderr}")
    return False


def extract_workspaces(content, cargo_toml):
    """
    Extract workspaces the Cargo.toml file.

    :param str content: The Cargo.toml parsed dictionnary
    :returns: The workspaces, otherwise None
    :rtype: [str]
    """

    try:
        members = []
        ws_path = cargo_toml.parent.absolute()
        # extract only binary crates
        for member in content['workspace']['members']:
            toml_path = ws_path.joinpath(member) / "Cargo.toml"
            if is_binary_crate(toml_path):
                members.append(member)
        return members
    except KeyError:
        return None


def extract_project_name(content):
    """
    Extract the Cargo project name from the Cargo.toml file.

    :param str content: The Cargo.toml parsed dictionnary
    :returns: The project name, otherwise None
    :rtype: str
    """
    try:
        return content['package']['name']
    except KeyError:
        return None


def extract_dependencies(content):
    """
    Extract the dependencies from the Cargo.toml file.

    :param str content: The Cargo.toml parsed dictionnary
    :returns: The dependencies name
    :rtype: list
    """
    return list(content['dependencies'].keys())
