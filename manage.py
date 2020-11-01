from flask_script import Manager
from flask_migrate import Migrate, MigrateCommand
from app import app, db

from flask_script import Command


class CreateSuperUser(Command):
    def run(self):
        username = input("Enter superuser user name : ")
        password = getpass("Enter superuser password : ")

        new_superuser = User(
            username=username, password=password, admin=True
        )

        new_superuser.save_to_db(db)
        print(f"superuser {username} created successfully")


migrate = Migrate(app, db)
manager = Manager(app)
manager.add_command("db", MigrateCommand)
manager.add_command("createsuperuser", CreateSuperUser)

if __name__ == "__main__":
    manager.run()
