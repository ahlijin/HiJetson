from setuptools import setup
package_name = 'fusion_node'
setup(
    name=package_name, version='0.0.1', packages=[package_name],
    data_files=[('share/ament_index/resource_index/packages', ['resource/' + package_name]), ('share/' + package_name, ['package.xml'])],
    install_requires=['setuptools'], zip_safe=True,
    maintainer='ahlij', maintainer_email='ahlij@example.com',
    description='Multi-modal fusion node',
    license='Apache-2.0', tests_require=['pytest'],
    entry_points={'console_scripts': ['fusion_node = fusion_node.fusion_node:main']},
)
