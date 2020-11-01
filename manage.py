from flask_script import Manager
from flask_migrate import Migrate, MigrateCommand
from getpass import getpass
from models import User
from app import app, db

from flask_script import Command


class CreateUser(Command):
    def run(self):
        username = input("Enter user username : ")
        password = getpass("Enter user password : ")
        admin = input("admin (y/n)?: ")

        new_superuser = User(
            username=username, password=password, admin=True if admin == 'y' else False
        )

        new_superuser.save_to_db(db)
        print(f"superuser {username} created successfully")


migrate = Migrate(app, db)
manager = Manager(app)
manager.add_command("db", MigrateCommand)
manager.add_command("createuser", CreateUser)

if __name__ == "__main__":
    manager.run()
