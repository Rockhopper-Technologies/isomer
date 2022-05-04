| |gh_actions| |codecov|

.. |gh_actions| image:: https://img.shields.io/github/workflow/status/Rockhopper-Technologies/isomer/Tests?event=push&logo=github-actions&style=plastic
    :target: https://github.com/Rockhopper-Technologies/isomer/actions/workflows/tests.yml
    :alt: GitHub Actions Status

.. |codecov| image:: https://img.shields.io/codecov/c/github/Rockhopper-Technologies/isomer.svg?style=plastic&logo=codecov
    :target: https://codecov.io/gh/Rockhopper-Technologies/isomer
    :alt: Coverage Status

Overview
========

ISOmer is a utility for creating ISO images based on an existing image or template.

It allows you to "flavor" a source directory to create a custom ISO in a repeatable, efficient way.


Usage
=====

Basic usage requires providing source directory, output file, and flavor.
Flavor can be a file name or path.
For more details see the `CLI Arguments`_ and `Flavor Configuration`_ sections.

.. code-block:: console

    $ isomer --source /mnt --outfile test.iso --flavor alma_9_custom


Basic Operation
===============

adjusting for exclusions and inclusions defined in the flavor config file. Source directories are
created independently, but files are symlinks to save space. All symlinks are resolved
when the ISO is created.

The ISO is created using the xorrisofs command, so it must be available in PATH. By default, a
checksum is generated and injected into the ISO using the implantisomd5 command.


CLI Arguments
=============

Required Arguments
------------------

| **-f FLAVOR or FILE**
| **--flavor FLAVOR or FILE**

    Specify flavor or flavor file to use.

    Flavor is evaluated in the following order, using the first one it finds.

    1. A file with the specified path
    2. A file with the format ``{flavor}.cfg`` is found in the current working directory
    3. A file with the format ``{flavor}.cfg`` is found in the configuration directory

    The configuration directory is the value of the ``ISOMER_CFG_DIR`` environment variable
    or ``/etc/isomer`` if unset.

    The tool will error if a configuration file can't be found or it fails to parse and validate.

| **-o FILE**
| **--outfile**

    ISO file to create

    Tool will error if the parent directory doesn't exist
    and will overwrite any existing file without prompting.

| **-s DIR**
| **--source DIR**

    Source directory to use as a template.

    This can be a mounted ISO, and extracted ISO, or an collection of files in a directory.

    The tool will error if the directory doesn't exist, but it does not check the contents.


Optional Arguments
------------------

| **-h**
| **--help**

    Show help message and exit

| **-q**
| **--quiet**

    Suppress output.

    Only critical error messages are displayed.

| **-w DIR**
| **--working DIR**

    Directory where files are prepared before ISO is created.

    By default, a temporary directory is used and removed after the ISO is created.
    When a working directory is used, any existing contents are removed before being populated.
    Any new contents are preserved after the ISO is generated.

    It is recommended to use this setting only for troubleshooting and special use cases.


Flavor Configuration
====================


File Format
-----------

Flavor configuration files use a subset of Python syntax.

For the most part, files are in the format ``IDENTIFIER = LITERAL`` where ``IDENTIFIER`` is a
valid Python variable name and ``LITERAL`` is a Python literal
(strings, bytes, numbers, tuples, lists, dicts, sets, booleans, and None)

Only specific function calls are supported. These are listed in the Functions_ section.

Python-style comments are supported.

Any unsupported syntax will raise an error.


Functions
---------

| **include**\ *('/path/to/flavor.cfg')*

    Include another flavor configuration at this location in the current file.

    If paths are relative, they are relative to the directory the current file is in.

    Example:

    .. code-block:: python

        include('/path/to/flavor.cfg')*


Comments
--------

Python-style comments are supported.

Comments start with a ``#`` and can start at any place in a line.

Example:

.. code-block:: python

    # This is a full line comment
    checksum = True  # This is an inline comment



Required Fields
---------------

| **volume_id** *'string'*

    Volume ID, passed to xorrisofs to set ISO metadata.

    Can not include any whitespace

    Available for use in ``grub_template``.

    Example:

    .. code-block:: python

        volume_id = 'test_1_2_3'


Optional Fields
---------------

| **bios_boot** *True|False*

    When True, boot options for bios boot are passed to xorrisofs.

    This does not verify other components required for BIOS boot are available in the ISO.

    Defaults to ``False``.

    Example:

    .. code-block:: python

        bios_boot = True

| **checksum** *True|False*

    When True, the ISO checksum is calculated and injected into the ISO after creation.

    This allows for checking the iso after downloading with a utility like ``checkisomd5``.

    Defaults to ``True``.

    Example:

    .. code-block:: python

        checksum = False

| **efi_boot** *True|False*

    When True, boot options for EFI boot are passed to xorrisofs.

    This does not verify other components required for EFI boot are available in the ISO.

    Defaults to ``True``.

    Example:

    .. code-block:: python

        efi_boot = True

| **exclude** *['relative_path', ...]*

    Source files to exclude from new ISO

    File paths should be relative to source directory.

    Single strings will be converted to single item lists

    Example:

    .. code-block:: python

        exclude = ['foo.txt', 'misc', 'boot/grub.cfg']

| **extra_fields** *{'iso_path': 'full_path', ...}*

    Extra variables to make available for substitution in ``grub_template``.

    Example:

    .. code-block:: python

            'build_version': '1.2.3',
            'config_opts': {'foo': 'bar', 'spam': 'eggs'},
            'major_ver': 1,
            'villains': ['Joker', 'Riddler', 'Penguin'],
        }

| **grub_template** *'string'*

    A template for creating ``EFI/BOOT/grub.cfg``

    ``grub_template`` allows variable substitution using the `Format Specification Mini-Language`_.

    By default, ``volume_id`` is the only variable available for substitution.
    If ``kickstart`` is set, ``ks_path`` is also available with a default value of ``'ks.cfg'``.
    Any fields in ``extra_fields`` are also available for substitution.

    `Format Specification Mini-Language`_

    Example:

    .. code-block:: python

        grub_template = '''
        menuentry 'Install {volume_id}' --hotkey=I  {{
            linuxefi /images/pxeboot/vmlinuz inst.stage2=hd:LABEL={volume_id} inst.ks=hd:LABEL={volume_id}:{ks_path} quiet
            initrdefi /images/pxeboot/initrd.img
        }}
        '''

.. _Format Specification Mini-Language: https://docs.python.org/3/library/string.html#formatspec

| **include** *{'iso_path': 'full_path', ...}*

    Additional files and directories to include in ISO

    These files and directories will we linked into the working directory.
    Any files or directories with the same path from the source will be replaced.

    Example:

    .. code-block:: python

        include = {
            'AppStream': '/srv/repos/Apps',
            'BaseOS': '/srv/repos/Base',
            '/certs/client.crt': '/srv/certs/iso.crt'
        }

| **kickstart** *'string'*

    Path to kickstart file.

    This is a shortcut for ``include = {'ks.cfg': '/path/to/kickstart'}``

    Kickstart path can be overridden with ``ks_path``.

    Available for use in ``grub_template``.

    Example:

    .. code-block:: python

        kickstart = '/path/to/kickstart'

| **ks_path** *'string'*

    Override for relative path of kickstart file.

    Available for use in ``grub_template``.

    Example:

    .. code-block:: python

        ks_path = 'relative/path/to/kickstart'


FAQ
===


Why is ISOmer called ISOmer?
----------------------------

We went looking for words in the dictionary with ISO in them. In chemistry, an isomer is a compound
that shares the same formula as another compound, but a different arrangement of atoms, resulting
in different properties. We thought that fit pretty well.
