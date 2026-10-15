package com.hekma.identity.repository;

import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.UserEntity;
import com.hekma.identity.domain.UserStatus;
import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Transactional
class UserRepositoryIntegrationTest {

    @Autowired
    private EntityManager entityManager;

    @Autowired
    private UserRepository userRepository;

    @Test
    @DisplayName("SQLRestriction filters out soft-deleted users from findById, findAll, and existsByEmail")
    void sqlRestriction_filtersOut_softDeletedUsers() {
        // 1. Create and persist active user
        UserEntity activeUser = UserEntity.builder()
                .firebaseUid("fb-active-01")
                .email("active@hekma.com")
                .role(Role.PATIENT)
                .status(UserStatus.ACTIVE)
                .isActive(true)
                .isDeleted(false)
                .build();
        entityManager.persist(activeUser);

        // 2. Create and persist soft-deleted user directly via entityManager
        UserEntity deletedUser = UserEntity.builder()
                .firebaseUid("fb-deleted-02")
                .email("deleted@hekma.com")
                .role(Role.PATIENT)
                .status(UserStatus.INACTIVE)
                .isActive(false)
                .isDeleted(true)
                .build();
        entityManager.persist(deletedUser);
        entityManager.flush();
        entityManager.clear();

        // 3. Verify findById excludes deleted user
        Optional<UserEntity> foundActive = userRepository.findById(activeUser.getId());
        Optional<UserEntity> foundDeleted = userRepository.findById(deletedUser.getId());

        assertThat(foundActive).isPresent();
        assertThat(foundDeleted).isEmpty();

        // 4. Verify findAll excludes deleted user
        List<UserEntity> allUsers = userRepository.findAll();
        assertThat(allUsers)
                .extracting(UserEntity::getEmail)
                .contains("active@hekma.com")
                .doesNotContain("deleted@hekma.com");

        // 5. Verify findByEmail and existsByEmail exclude deleted user
        assertThat(userRepository.findByEmail("deleted@hekma.com")).isEmpty();
        assertThat(userRepository.existsByEmail("deleted@hekma.com")).isFalse();
    }

    @Test
    @DisplayName("Setting isDeleted=true excludes user from subsequent JPA repository queries")
    void softDelete_excludesUserFromQueries() {
        UserEntity user = UserEntity.builder()
                .firebaseUid("fb-to-soft-delete-03")
                .email("softdelete@hekma.com")
                .role(Role.SITE)
                .status(UserStatus.ACTIVE)
                .isActive(true)
                .isDeleted(false)
                .build();
        entityManager.persist(user);
        entityManager.flush();
        UUID userId = user.getId();
        entityManager.clear();

        // Verify initially present
        assertThat(userRepository.findById(userId)).isPresent();

        // Mark as soft deleted directly in database
        entityManager.createQuery("UPDATE UserEntity u SET u.isDeleted = true, u.isActive = false WHERE u.id = :id")
                .setParameter("id", userId)
                .executeUpdate();
        entityManager.flush();
        entityManager.clear();

        // Querying via JPA repository should now return empty due to @SQLRestriction
        Optional<UserEntity> queried = userRepository.findById(userId);
        assertThat(queried).isEmpty();
        assertThat(userRepository.findByEmail("softdelete@hekma.com")).isEmpty();
    }
}
