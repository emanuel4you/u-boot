# SPDX-License-Identifier:	GPL-2.0+
#
# Copyright (c) 2021 Alexandru Gagniuc <mr.nuke.me@gmail.com>

"""
Check hashes produced by mkimage against known values

This test checks the correctness of mkimage's hashes. by comparing the mkimage
output of a fixed data block with known good hashes.
This test doesn't run the sandbox. It only checks the host tool 'mkimage'
"""

import os
import pytest
import utils

kernel_hashes = {
    "sha512" : "f18c1486a2c29f56360301576cdfce4dfd8e8e932d0ed8e239a1f314b8ae1d77b2a58cd7fe32e4075e69448e623ce53b0b6aa6ce5626d2c189a5beae29a68d93",
    "sha384" : "16e28976740048485d08d793d8bf043ebc7826baf2bc15feac72825ad67530ceb3d09e0deb6932c62a5a0e9f3936baf4",
    "sha256" : "2955c56bc1e5050c111ba6e089e0f5342bb47dedf77d87e3f429095feb98a7e5",
    "sha1"   : "652383e1a6d946953e1f65092c9435f6452c2ab7",
    "md5"    : "4879e5086e4c76128e525b5fe2af55f1",
    "crc32"  : "32eddfdf",
    "crc16-ccitt" : "d4be"
}

class ReadonlyFitImage(object):
    """ Helper to manipulate a FIT image on disk """
    def __init__(self, ubman, file_name):
        self.fit = file_name
        self.ubman = ubman
        self.hashable_nodes = set()

    def __fdt_list(self, path):
        return utils.run_and_log(self.ubman, f'fdtget -l {self.fit} {path}')

    def __fdt_get(self, node, prop):
        val = utils.run_and_log(self.ubman, f'fdtget {self.fit} {node} {prop}')
        return val.rstrip('\n')

    def __fdt_get_sexadecimal(self, node, prop):
        numbers = utils.run_and_log(self.ubman,
                                    f'fdtget -tbx {self.fit} {node} {prop}')

        sexadecimal = ''
        for num in numbers.rstrip('\n').split(' '):
            sexadecimal += num.zfill(2)
        return sexadecimal

    def find_hashable_image_nodes(self):
        for node in self.__fdt_list('/images').split():
            # We only have known hashes for the kernel node
            if 'kernel' not in node:
                continue
            self.hashable_nodes.add(f'/images/{node}')

        return self.hashable_nodes

    def verify_hashes(self):
        for image in self.hashable_nodes:
            algos = set()
            for node in self.__fdt_list(image).split():
                if "hash-" not in node:
                    continue

                raw_hash = self.__fdt_get_sexadecimal(f'{image}/{node}', 'value')
                algo = self.__fdt_get(f'{image}/{node}', 'algo')
                algos.add(algo)

                good_hash = kernel_hashes[algo]
                if good_hash != raw_hash:
                    raise ValueError(f'{image} Borked hash: {algo}');

            # Did we test all the hashes we set out to test?
            missing_algos = kernel_hashes.keys() - algos
            if (missing_algos):
                raise ValueError(f'Missing hashes from FIT: {missing_algos}')


@pytest.mark.buildconfigspec('hash')
@pytest.mark.requiredtool('dtc')
@pytest.mark.requiredtool('fdtget')
@pytest.mark.requiredtool('fdtput')
def test_mkimage_hashes(ubman):
    """ Test that hashes generated by mkimage are correct. """

    def assemble_fit_image(dest_fit, its, destdir):
        dtc_args = f'-I dts -O dtb -i {destdir}'
        utils.run_and_log(ubman, [mkimage, '-D', dtc_args, '-f', its, dest_fit])

    def dtc(dts):
        dtb = dts.replace('.dts', '.dtb')
        utils.run_and_log(ubman,
                          f'dtc {datadir}/{dts} -O dtb -o {tempdir}/{dtb}')

    mkimage = ubman.config.build_dir + '/tools/mkimage'
    datadir = ubman.config.source_dir + '/test/py/tests/vboot/'
    tempdir = os.path.join(ubman.config.result_dir, 'hashes')
    os.makedirs(tempdir, exist_ok=True)

    fit_file = f'{tempdir}/test.fit'
    dtc('sandbox-kernel.dts')

    # Create a fake kernel image -- Avoid zeroes or crc16 will be zero
    with open(f'{tempdir}/test-kernel.bin', 'w') as fd:
        fd.write(500 * chr(0xa5))

    assemble_fit_image(fit_file, f'{datadir}/hash-images.its', tempdir)

    fit = ReadonlyFitImage(ubman, fit_file)
    nodes = fit.find_hashable_image_nodes()
    if len(nodes) == 0:
        raise ValueError('FIT image has no "/image" nodes with "hash-..."')

    fit.verify_hashes()
